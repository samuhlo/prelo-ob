"""Exercise the built service in an isolated container with a temporary managed volume."""
import argparse
import json
import secrets
import subprocess
import tempfile
import time
from pathlib import Path
from restore_backup import restore

PROBE = r'''
import base64,hashlib,io,json,os,time,urllib.request,urllib.error,uuid,zipfile
from pathlib import Path
from PIL import Image
from margen.models import PublicationRequest,EditorialPlan
from margen.epub import build_epub
TOKEN=os.environ['MARGEN_TOKEN']
def api(route,body=None,binary=False):
    req=urllib.request.Request('http://127.0.0.1:8765'+route,data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=15) as response:data=response.read()
    return data if binary else json.loads(data)
for _ in range(30):
    try:health=api('/health');break
    except OSError:time.sleep(.2)
else:raise RuntimeError('Service did not become ready')
try:urllib.request.urlopen('http://127.0.0.1:8765/v1/library',timeout=5)
except urllib.error.HTTPError as e:assert e.code==401
else:raise AssertionError('Authentication missing')
note=dict(id=str(uuid.uuid4()),path='synthetic.md',title='Prueba de lectura',markdown='Texto sintético.\n\n| Tema | Valor |\n|---|---|\n| Equipos | 5 |\n\n```sh\nip route show\n```')
payload=dict(notes=[note],send_to_kobo=True)
publication=api('/v1/publications',payload)
epub=api('/v1/publications/'+publication['id']+'/epub',binary=True)
Path('/tmp/study.epub').write_bytes(epub)
checksum=hashlib.sha256(epub).hexdigest()
api('/v1/deliveries/'+publication['id']+'/claim',{'device':'synthetic-reader'})
api('/v1/deliveries/'+publication['id']+'/receipt',{'device':'synthetic-reader','checksum':checksum})
api('/v1/publications/'+publication['id']+'/action',{'action':'pin'})
api('/v1/device/inventory',{'device':'synthetic-reader','books':[{'id':'file:///mnt/onboard/'+publication['filename'],
    'path':publication['filename'],'edition':publication['id'],'title':'Synthetic','present':True,'sha256':checksum}]})
command=api('/v1/kobo/removals',{'path':publication['filename'],'device':'synthetic-reader'})
claim=api('/v1/kobo/commands/'+command['id']+'/claim',{'device':'synthetic-reader'})
assert claim['state']=='executing'
api('/v1/kobo/commands/'+command['id']+'/done',{'ok':True,'device':'synthetic-reader','claim_token':claim['claim_token']})
annotation=api('/v1/annotations',{'highlights':[{'id':'quote1','volume_id':publication['filename'],'text':'Texto sintético.'}]})
assert annotation['highlights'][0]['source']['id']==note['id']
jobid=str(uuid.uuid4());api('/v1/jobs',{'id':jobid,'publication':payload})
for _ in range(100):
    job=api('/v1/jobs/'+jobid)
    if job['state']=='complete':break
    assert job['state']!='failed'
    time.sleep(.05)
assert job['state']=='complete'
req=urllib.request.Request('http://127.0.0.1:8765/v1/kobo/uploads?device=synthetic-reader&filename=extra.epub',data=epub,
    headers={'Authorization':'Bearer '+TOKEN,'Content-Type':'application/epub+zip'})
with urllib.request.urlopen(req,timeout=15) as r:upload=json.load(r)
Path('/tmp/backup.zip').write_bytes(api('/v1/backup',binary=True))
req=PublicationRequest(**{**payload,'style':'retro90','artwork':'generated'})
visuals=[dict(id='cover',placement='cover',source_ids=[note['id']],concept='Tema',description='Synthetic',caption=''),
         dict(id='inside',placement='inside',source_ids=[note['id']],concept='Tema',description='Synthetic',caption='Una figura de prueba con acentos: conexión y edición.')]
plan=EditorialPlan(title='Lectura de prueba',subtitle='Comprobación sintética',chapters=[dict(title='Tema',source_ids=[note['id']])],visuals=visuals)
image=io.BytesIO();Image.new('RGB',(320,400),'#87b9ae').save(image,format='JPEG')
art=[{**v,'data':base64.b64encode(image.getvalue()).decode(),'media_type':'image/jpeg'} for v in visuals]
record=build_epub(req,plan,str(uuid.uuid4()),Path('/tmp/retro'),art)
Path('/tmp/retro.epub').write_bytes((Path('/tmp/retro')/record['filename']).read_bytes())
print(json.dumps({'version':health['version'],'editions':len(api('/v1/library')['publications']),
                  'annotations':len(annotation['highlights']),'pending_upload':upload['id'],'state':'passed'}))
'''


def docker(*args, timeout=30):
    return subprocess.run(['docker', *map(str,args)],capture_output=True,text=True,check=True,timeout=timeout)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',default='prelo-ci')
    parser.add_argument('--build',action='store_true')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    if args.build:docker('build','-t',args.image,root/'server',timeout=420)
    identity='prelo-test-'+secrets.token_hex(6)
    volume=identity+'-data';created=False
    docker('volume','create',volume)
    try:
        docker('create','--name',identity,'--network','none','--label','local.prelo.purpose=beta-test',
               '--mount',f'type=volume,source={volume},target=/data','-e','MARGEN_TOKEN=synthetic-'+'x'*40,
               '-e','AI_PROVIDER=disabled',args.image)
        created=True
        with tempfile.TemporaryDirectory(prefix='prelo-smoke-') as temporary:
            temporary=Path(temporary);(temporary/'probe.py').write_text(PROBE)
            docker('cp',temporary/'probe.py',identity+':/tmp/probe.py');docker('start',identity)
            result=json.loads(docker('exec',identity,'python','/tmp/probe.py',timeout=90).stdout)
            assert result['version']==json.loads((root/'manifest.json').read_text())['version']
            docker('cp',identity+':/tmp/backup.zip',temporary/'backup.zip')
            restored=temporary/'restored';counts=restore(temporary/'backup.zip',restored)
            assert counts['editions']==2 and counts['annotations']==1
            assert (restored/'.uploads'/(result.pop('pending_upload')+'.epub')).is_file()
            recovered_name, recovered_volume = identity+'-restored', volume+'-restored'
            recovered_created = False
            docker('volume','create',recovered_volume)
            try:
                docker('create','--name',recovered_name,'--network','none','--label','local.prelo.purpose=beta-test',
                       '--mount',f'type=volume,source={recovered_volume},target=/data',
                       '-e','MARGEN_TOKEN=synthetic-'+'x'*40,'-e','AI_PROVIDER=disabled',args.image)
                recovered_created = True
                docker('cp',str(restored)+'/.',recovered_name+':/data/')
                docker('start',recovered_name)
                # Ownership adjustment is confined to the disposable managed volume, never the host.
                docker('exec','--user','0',recovered_name,'chown','-R','10001:10001','/data')
                recovery_probe = PROBE.split('note=dict(')[0] + """
dashboard=api('/v1/library')
pending=api('/v1/kobo/commands?device=synthetic-reader')
assert len(dashboard['publications'])==2 and len(pending)==1
assert hashlib.sha256(api('/v1/kobo/uploads/'+pending[0]['id'],binary=True)).hexdigest()==pending[0]['sha256']
quotes=sum(len(api('/v1/kobo/highlights?volume='+p['filename'])['highlights']) for p in dashboard['publications'])
assert quotes==1
print(json.dumps({'state':'passed'}))
"""
                (temporary/'recovery.py').write_text(recovery_probe)
                docker('cp',temporary/'recovery.py',recovered_name+':/tmp/recovery.py')
                assert json.loads(docker('exec',recovered_name,'python','/tmp/recovery.py',timeout=90).stdout)['state']=='passed'
                result['restored_service']='passed'
            finally:
                if recovered_created:docker('rm','-f',recovered_name,timeout=15)
                docker('volume','rm',recovered_volume,timeout=15)
            if args.output:
                args.output.mkdir(parents=True,exist_ok=True)
                for name in ['study.epub','retro.epub']:docker('cp',identity+':/tmp/'+name,args.output/name)
                (args.output/'result.json').write_text(json.dumps(result,indent=2))
            print(json.dumps(result))
    finally:
        if created:docker('rm','-f',identity,timeout=15)
        docker('volume','rm',volume,timeout=15)


if __name__=='__main__':main()
