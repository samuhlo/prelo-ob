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


def release_gate_source():
    """Execute the actual release step, including its one-version owner exception."""
    import textwrap
    workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/release.yml').read_text()
    return textwrap.dedent(workflow.split("python - <<'PY'\n",1)[1].split('\n          PY',1)[0])


def test_release_allows_only_the_documented_clean_install_waiver(tmp_path, monkeypatch):
    import pytest
    record=fixture(tmp_path)
    install=record['checks']['clean_mac_install']
    install.update(status='waived',approved_by='owner')
    def save():
        (tmp_path/'docs/beta-acceptance.json').write_text(json.dumps(record))
    monkeypatch.chdir(tmp_path)
    save()
    exec(compile(release_gate_source(),'release_acceptance','exec'),{})
    # Other pending checks, unapproved exceptions and older/future versions stay blocked.
    record['checks']['usb_roundtrip']['status']='pending';save()
    with pytest.raises(SystemExit):exec(compile(release_gate_source(),'release_acceptance','exec'),{})
    record['checks']['usb_roundtrip']['status']='passed'
    install.pop('approved_by');save()
    with pytest.raises(SystemExit):exec(compile(release_gate_source(),'release_acceptance','exec'),{})
    install['approved_by']='owner'
    for version in ['0.11.0','1.1.0']:
        record['version']=version
        (tmp_path/'manifest.json').write_text(json.dumps({'version':version}))
        record['product_sha256']=product_digest(tmp_path);save()
        with pytest.raises(SystemExit):exec(compile(release_gate_source(),'release_acceptance','exec'),{})
    record['version']='1.0.0'
    (tmp_path/'manifest.json').write_text(json.dumps({'version':'1.0.0'}))
    record['product_sha256']=product_digest(tmp_path);save()
    (tmp_path/'server/margen/app.py').write_text('# Changed after acceptance')
    with pytest.raises(SystemExit):exec(compile(release_gate_source(),'release_acceptance','exec'),{})
