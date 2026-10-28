"""Release gate: manual acceptance belongs to this version and these product sources."""
import argparse
import hashlib
import json
from pathlib import Path
from public_files import public_files

REQUIRED = ('clean_mac_install','obsidian_upgrade','usb_roundtrip','backup_recovery')


def product_digest(root):
    digest=hashlib.sha256()
    for path in public_files(root):
        name=path.relative_to(root).as_posix()
        runtime = name.startswith(('plugin/', 'server/', 'scripts/', 'assets/')) and not name.startswith(('plugin/tests/', 'server/tests/'))
        if runtime or name in {'compose.yaml', 'Instalar Prelo.command', '.env.example', 'manifest.json'}:
            digest.update(name.encode()+b'\0'+path.read_bytes()+b'\0')
    return digest.hexdigest()


def check(root):
    record=json.loads((root/'docs/beta-acceptance.json').read_text())
    errors=[]
    if record.get('version')!=json.loads((root/'manifest.json').read_text())['version']:errors.append('La aceptación pertenece a otra versión.')
    if record.get('product_sha256')!=product_digest(root):errors.append('La aceptación no corresponde a estos archivos del producto.')
    for name in REQUIRED:
        item=record.get('checks',{}).get(name,{})
        if item.get('status')!='passed' or not item.get('date') or not item.get('summary'):
            errors.append('Pendiente: '+name)
    return errors


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--digest',action='store_true');args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    if args.digest:print(product_digest(root))
    else:
        errors=check(root)
        for error in errors:print(error)
        raise SystemExit(bool(errors))
