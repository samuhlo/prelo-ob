"""Build deterministic public release archives, never the private connection package."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from audit_public import audit
from public_files import public_files

ROOT = Path(__file__).resolve().parents[1]


def add(archive, path, name):
    info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (0o100755 if path.suffix == '.command' else 0o100644) << 16
    archive.writestr(info, path.read_bytes())


def build(root=ROOT):
    root = Path(root)
    findings = audit(root)
    if findings:
        raise ValueError('Public source audit failed: ' + ', '.join(path for path, _ in findings))
    manifest = json.loads((root / 'manifest.json').read_text(encoding="utf-8-sig"))
    if manifest != json.loads((root / 'dist/margen/manifest.json').read_text(encoding="utf-8-sig")):
        raise ValueError('Build the plugin again: the release manifest is stale.')
    version = manifest['version']
    out = root / 'dist/releases' / version
    out.mkdir(parents=True, exist_ok=True)
    plugin_files = ['main.js', 'manifest.json', 'styles.css']
    for name in plugin_files:
        shutil.copyfile(root / 'dist/margen' / name, out / name)
    with zipfile.ZipFile(out / f'prelo-plugin-{version}.zip', 'w') as archive:
        for name in plugin_files:
            add(archive, out / name, 'margen/' + name)
        add(archive, root / 'LICENSE', 'margen/LICENSE')
        add(archive, root / 'THIRD_PARTY_NOTICES.md', 'margen/THIRD_PARTY_NOTICES.md')
    with zipfile.ZipFile(out / f'prelo-macos-{version}.zip', 'w') as archive:
        for path in public_files(root):
            add(archive, path, f'prelo-{version}/' + path.relative_to(root).as_posix())
        for name in plugin_files:
            add(archive, out / name, f'prelo-{version}/dist/margen/' + name)
    assets = [*plugin_files, f'prelo-plugin-{version}.zip', f'prelo-macos-{version}.zip']
    (out / 'SHA256SUMS').write_text(''.join(hashlib.sha256((out / name).read_bytes()).hexdigest() + '  ' + name + '\n' for name in assets))
    for name in assets:
        if name.endswith('.zip'):
            with zipfile.ZipFile(out / name) as archive:
                assert archive.testzip() is None
                assert not any('/data/' in p or p.endswith('/.env') or p.endswith('conexion-prelo.json') for p in archive.namelist())
    print(f'Public release {version}: {out}')
    return out


if __name__ == '__main__':
    build()
