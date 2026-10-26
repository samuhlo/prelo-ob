"""Failure injection for complete installation using temporary vaults and fake native/Docker calls."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import install as installer
import install_transaction as transaction
import install_usb


@pytest.fixture
def setup(tmp_path, monkeypatch):
    home=tmp_path/'home';home.mkdir()
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:home))
    monkeypatch.setattr(install_usb.sys,'platform','darwin')
    vault=tmp_path/'vault';(vault/'.obsidian/plugins/margen').mkdir(parents=True)
    plugin=vault/'.obsidian/plugins/margen'
    for name in ['main.js','styles.css','manifest.json']:(plugin/name).write_text('old-'+name)
    (plugin/'data.json').write_text(json.dumps({'settings':{'outputFolder':'Custom/Books'},'composer':{'paths':['keep.md']}}))
    (vault/'.obsidian/community-plugins.json').write_text('["another-plugin","margen"]')
    runtime=tmp_path/'runtime';(runtime/'app/dist/margen').mkdir(parents=True);(runtime/'server').mkdir()
    (runtime/'app/compose.yaml').write_text('old-compose')
    for name in ['main.js','styles.css','manifest.json']:(runtime/'app/dist/margen'/name).write_text('old-'+name)
    (runtime/'server/old-runtime').write_text('old-python')
    (runtime/'service.env').write_text('MARGEN_TOKEN='+'x'*32+'\nAI_PROVIDER=disabled\n')
    (runtime/'installation.json').write_text(json.dumps({'version':'0.10.0','docker_context':'fixture','state':'ready'}))
    (runtime/'usb.json').write_text(json.dumps({'vault':str(vault),'highlights_folder':'Custom/Quotes'}))
    agents=home/'Library/LaunchAgents';agents.mkdir(parents=True)
    for label in transaction.LABELS:(agents/(label+'.plist')).write_bytes(b'old-agent')
    root=tmp_path/'download';(root/'dist/margen').mkdir(parents=True);(root/'server').mkdir();(root/'assets').mkdir();(root/'scripts').mkdir()
    manifest=json.dumps({'id':'margen','version':'0.10.1'})
    (root/'manifest.json').write_text(manifest);(root/'compose.yaml').write_text('new-compose')
    for name in installer.PLUGIN_FILES:(root/'dist/margen'/name).write_text(manifest if name=='manifest.json' else 'new-'+name)
    (root/'server/pyproject.toml').write_text('new-source')
    for name in ['install.py','install_common.py','install_plugin.py','install_bridge.py','install_usb.py','run_bridge.py','install_transaction.py']:
        (root/'scripts'/name).write_text('# synthetic installer fixture')
    calls=[];failure={'stage':None,'fired':False}
    def fail(stage):
        if failure['stage']==stage and not failure['fired']:
            failure['fired']=True;raise RuntimeError('Synthetic '+stage+' failure')
    def run(args,**kwargs):
        args=list(map(str,args));calls.append(args)
        if 'up' in args and '--build' in args:fail('container')
        if 'exec' in args:fail('package')
        if 'config' in args:return SimpleNamespace(stdout=json.dumps({'services':{'margen':{'volumes':[{'type':'volume'}]}}}),returncode=0)
        if 'inspect' in args:return SimpleNamespace(stdout='sha256:'+'a'*64,returncode=0)
        if 'ps' in args:return SimpleNamespace(stdout='old-container',returncode=0)
        return SimpleNamespace(stdout='',returncode=0)
    def bridge(rt,*args,**kwargs):
        py=rt/'server/.venv/bin/python';py.parent.mkdir(parents=True,exist_ok=True);py.write_text('new-python')
        fail('native')
    usb=installer.install_usb;plugin_install=installer.install_plugin
    def install_usb_stub(*args,**kwargs):result=usb(*args,**kwargs);fail('usb');return result
    def install_plugin_stub(*args,**kwargs):result=plugin_install(*args,**kwargs);fail('plugin');return result
    monkeypatch.setattr(installer,'preflight',lambda *args:'fixture');monkeypatch.setattr(installer,'occupied',lambda _:True)
    monkeypatch.setattr(installer,'request',lambda *args:{'jobs':[],'device':{'state':'disconnected'}})
    monkeypatch.setattr(installer,'backup_library',lambda destination,token:destination.write_bytes(b'synthetic backup'))
    monkeypatch.setattr(installer,'run',run);monkeypatch.setattr(transaction,'run',run)
    monkeypatch.setattr(transaction,'load_agent',lambda *args:None);monkeypatch.setattr(install_usb,'load_agent',lambda *args:None)
    monkeypatch.setattr(installer,'install_bridge',bridge);monkeypatch.setattr(installer,'install_usb',install_usb_stub)
    monkeypatch.setattr(installer,'install_plugin',install_plugin_stub)
    return root,vault,runtime,calls,failure


@pytest.mark.parametrize('stage',['native','container','package','usb','plugin'])
def test_failure_restores_files_agents_and_previous_image(setup,stage):
    root,vault,runtime,calls,failure=setup;failure['stage']=stage
    previous=(vault/'.obsidian/plugins/margen/data.json').read_bytes()
    with pytest.raises(RuntimeError,match='Synthetic'):installer.install_service(vault,root=root,runtime=runtime,ai='none')
    assert (runtime/'server/old-runtime').read_text()=='old-python'
    assert (runtime/'app/compose.yaml').read_text()=='old-compose'
    assert (vault/'.obsidian/plugins/margen/main.js').read_text()=='old-main.js'
    assert (vault/'.obsidian/plugins/margen/data.json').read_bytes()==previous
    assert json.loads((runtime/'installation.json').read_text())['version']=='0.10.0'
    assert not (runtime/'update-in-progress.json').exists()
    assert any('--no-build' in args for args in calls)
    assert not any('-v' in args or '--volumes' in args for args in calls)
    for label in transaction.LABELS:assert (Path.home()/'Library/LaunchAgents'/(label+'.plist')).read_bytes()==b'old-agent'


def test_success_preserves_custom_folders_and_removes_journal(setup):
    root,vault,runtime,_,_=setup
    installer.install_service(vault,root=root,runtime=runtime,ai='none')
    settings=json.loads((vault/'.obsidian/plugins/margen/data.json').read_text())['settings']
    assert settings['outputFolder']=='Custom/Books' and settings['highlightsFolder']=='Custom/Quotes'
    assert not (runtime/'update-in-progress.json').exists()


def test_interrupted_install_requires_explicit_recovery(setup):
    root,vault,runtime,_,_=setup
    transaction.capture(runtime,vault,'fixture','sha256:'+'a'*64)
    (runtime/'app/compose.yaml').write_text('interrupted')
    with pytest.raises(ValueError,match='--recover'):installer.install_service(vault,root=root,runtime=runtime)
    transaction.recover(runtime)
    assert (runtime/'app/compose.yaml').read_text()=='old-compose'


def test_busy_service_is_rejected_before_mutation(setup,monkeypatch):
    root,vault,runtime,calls,_=setup
    monkeypatch.setattr(installer,'request',lambda *args:{'jobs':[{'state':'running'}],'device':{}})
    with pytest.raises(ValueError,match='Espera'):installer.install_service(vault,root=root,runtime=runtime)
    assert not (runtime/'update-in-progress.json').exists()
    assert not any('up' in args for args in calls)


def test_recovery_never_starts_an_old_bind_mount(setup,monkeypatch):
    _,vault,runtime,calls,_=setup
    transaction.capture(runtime,vault,'fixture','sha256:'+'a'*64)
    original=transaction.run
    def run(args,**kwargs):
        if 'config' in args:return SimpleNamespace(stdout=json.dumps({'services':{'margen':{'volumes':[{'type':'bind'}]}}}))
        return original(args,**kwargs)
    monkeypatch.setattr(transaction,'run',run)
    with pytest.raises(ValueError,match='bind mounts'):transaction.recover(runtime)
    assert (runtime/'update-in-progress.json').exists()
    assert not any('up' in args for args in calls)
