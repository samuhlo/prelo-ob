"""Explicit publication boundary: local reports, credentials and history stay private."""
from pathlib import Path

ROOT_FILES = {'.env.example', '.gitignore', 'AGENTS.md', 'README.md', 'CHANGELOG.md', 'LICENSE',
              'THIRD_PARTY_NOTICES.md', 'manifest.json', 'versions.json', 'compose.yaml', 'Instalar Prelo.command'}
DOCS = {'producto.md', 'revista-90s.md', 'instalacion.md', 'desarrollo.md', 'privacidad.md', 'validacion-publica.md'}
SCRIPTS = {'install.py', 'install_common.py', 'install_plugin.py', 'install_bridge.py', 'install_usb.py',
           'run_bridge.py', 'setup.py', 'publish_local.py', 'render_cover.mjs', 'restore_backup.py',
           'set_version.py', 'validate_epub.py', 'check_caption_layout.py', 'public_files.py', 'build_release.py', 'audit_public.py'}
IGNORED = {'.venv', 'node_modules', '__pycache__', '.pytest_cache', '.ruff_cache', 'data', 'dist', '.git'}


def public_files(root):
    root = Path(root).resolve()
    result = [root / name for name in ROOT_FILES if (root / name).is_file()]
    for directory in ['assets', 'server', 'plugin', 'tests', '.github']:
        if not (root / directory).exists():
            continue
        for path in (root / directory).rglob('*'):
            relative = path.relative_to(root)
            if not path.is_file() or any(part in IGNORED or part.endswith('.egg-info') for part in relative.parts):
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError('A public source cannot be a symlink: ' + str(relative))
            if path.suffix in {'.pyc', '.log'} or path.name in {'.DS_Store', 'main.js', 'sql-wasm.wasm'}:
                continue
            result.append(path)
    result += [root / 'docs' / name for name in DOCS if (root / 'docs' / name).is_file()]
    result += [root / 'scripts' / name for name in SCRIPTS if (root / 'scripts' / name).is_file()]
    return sorted(set(result))
