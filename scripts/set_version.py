"""Prepare a numeric release version consistently; never publish or install it."""
import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def set_version(version, root=ROOT):
    if not re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', version):
        raise ValueError('Usa una versión major.minor.patch, sin prefijo v.')
    root = Path(root)
    updates = {}
    for name in ['manifest.json', 'plugin/manifest.json', 'plugin/package.json', 'plugin/package-lock.json']:
        data = json.loads((root / name).read_text())
        data['version'] = version
        if name.endswith('package-lock.json'):
            data['packages']['']['version'] = version
        updates[name] = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    versions = json.loads((root / 'versions.json').read_text())
    versions[version] = json.loads(updates['manifest.json'])['minAppVersion']
    updates['versions.json'] = json.dumps(versions, indent=2) + '\n'
    updates['server/margen/__init__.py'] = f'__version__ = "{version}"\n'
    updates['server/pyproject.toml'] = re.sub(r'^version = "[^"]+"', f'version = "{version}"',
        (root / 'server/pyproject.toml').read_text(), count=1, flags=re.M)
    updates['server/uv.lock'] = re.sub(r'(name = "margen-server"\nversion = ")[^"]+',
        lambda m: m[1] + version, (root / 'server/uv.lock').read_text(), count=1)
    acceptance = root / "docs/beta-acceptance.json"
    if acceptance.exists():
        value = json.loads(acceptance.read_text())
        if value.get("version") != version:
            value["version"] = version
            value["product_sha256"] = ""
            for item in value.get("checks", {}).values():
                item.update(status="pending", date="", summary="Revalidar para esta versión.")
            updates["docs/beta-acceptance.json"] = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    for name, content in updates.items():
        (root / name).write_text(content)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version')
    args = parser.parse_args()
    set_version(args.version)
    print('Versión preparada. Actualiza CHANGELOG, ejecuta las pruebas y genera los paquetes antes de publicar.')
