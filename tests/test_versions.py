import importlib.util
import json
from pathlib import Path
import shutil
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('set_version', ROOT / 'scripts/set_version.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_set_version_updates_only_release_metadata(tmp_path):
    files = ['manifest.json', 'plugin/manifest.json', 'plugin/package.json', 'plugin/package-lock.json',
             'versions.json', 'server/margen/__init__.py', 'server/pyproject.toml', 'server/uv.lock']
    for name in files:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    module.set_version('0.10.0', tmp_path)
    for name in files[:4]:
        assert json.loads((tmp_path / name).read_text())['version'] == '0.10.0'
    assert json.loads((tmp_path / 'plugin/package-lock.json').read_text())['packages']['']['version'] == '0.10.0'
    assert 'name = "margen-server"\nversion = "0.10.0"' in (tmp_path / 'server/uv.lock').read_text()
    assert json.loads((tmp_path / 'versions.json').read_text())['0.7.0'] == '1.8.0'
    before = (tmp_path / 'manifest.json').read_bytes()
    with pytest.raises(ValueError): module.set_version('v1.0', tmp_path)
    assert (tmp_path / 'manifest.json').read_bytes() == before
