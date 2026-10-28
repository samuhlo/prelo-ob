import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from check_beta import check, product_digest, REQUIRED


def fixture(root):
    (root/'docs').mkdir();(root/'server/margen').mkdir(parents=True)
    (root/'manifest.json').write_text('{"version":"1.0.0"}')
    (root/'server/margen/app.py').write_text('# product code')
    record={'version':'1.0.0','product_sha256':product_digest(root),'checks':{
        name:{'status':'passed','date':'2026-10-26','summary':'Synthetic acceptance fixture'} for name in REQUIRED}}
    (root/'docs/beta-acceptance.json').write_text(json.dumps(record))
    return record


def test_acceptance_requires_this_product_and_version(tmp_path):
    record=fixture(tmp_path);assert check(tmp_path)==[]
    (tmp_path/'server/margen/app.py').write_text('# changed product')
    assert check(tmp_path)
    record['product_sha256']=product_digest(tmp_path);record['version']='0.9.0'
    (tmp_path/'docs/beta-acceptance.json').write_text(json.dumps(record));assert check(tmp_path)


def test_pending_manual_checks_cannot_publish(tmp_path):
    record=fixture(tmp_path);record['checks']['usb_roundtrip']['status']='pending'
    (tmp_path/'docs/beta-acceptance.json').write_text(json.dumps(record))
    assert 'Pendiente: usb_roundtrip' in check(tmp_path)


def test_preparing_another_version_invalidates_manual_acceptance(tmp_path):
    import shutil
    from set_version import set_version
    root=Path(__file__).resolve().parents[1]
    for name in ['manifest.json','plugin/manifest.json','plugin/package.json','plugin/package-lock.json','versions.json','server/margen/__init__.py','server/pyproject.toml','server/uv.lock','docs/beta-acceptance.json']:
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/name,target)
    record=json.loads((tmp_path/'docs/beta-acceptance.json').read_text())
    record['checks']['usb_roundtrip']['status']='passed'
    (tmp_path/'docs/beta-acceptance.json').write_text(json.dumps(record))
    set_version('0.12.0',tmp_path)
    changed=json.loads((tmp_path/'docs/beta-acceptance.json').read_text())
    assert changed['version']=='0.12.0' and not changed['product_sha256']
    assert all(item['status']=='pending' for item in changed['checks'].values())
