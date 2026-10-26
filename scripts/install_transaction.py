"""Private recovery journal for the public installer; never snapshots the user's notes."""
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from install_common import load_agent, run, write_private

LABELS = ('local.prelo.kobo', 'local.prelo.codex-bridge')


def targets(runtime, vault):
    result = {name: runtime / name for name in ['app', 'server', 'scripts', 'service.env', '.env', 'usb.json', 'conexion-prelo.json', 'installation.json']}
    result['plugin'] = vault / '.obsidian/plugins/margen'
    result['community-plugins.json'] = vault / '.obsidian/community-plugins.json'
    result.update({label: Path.home() / 'Library/LaunchAgents' / (label + '.plist') for label in LABELS})
    return result


def capture(runtime, vault, context, image):
    directory = runtime / 'backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') / 'transaction'
    directory.mkdir(parents=True, mode=0o700)
    existing = []
    for name, target in targets(runtime, vault).items():
        if target.is_symlink():
            raise ValueError('Una ruta de instalación es un enlace simbólico; no se sustituirá.')
        if target.is_dir():
            shutil.copytree(target, directory / name, symlinks=True)
            existing.append(name)
        elif target.is_file():
            shutil.copy2(target, directory / name)
            existing.append(name)
    value = {'vault': str(vault), 'context': context, 'image': image,
             'backup': str(directory), 'existing': existing}
    write_private(runtime / 'update-in-progress.json', json.dumps(value))
    return directory


def stop_agents():
    for label in LABELS:
        run(['launchctl', 'bootout', f'gui/{os.getuid()}/{label}'], timeout=15, check=False)


def recover(runtime):
    runtime = Path(runtime).resolve()
    journal = runtime / 'update-in-progress.json'
    value = json.loads(journal.read_text())
    backup = Path(value['backup']).resolve()
    if not backup.is_relative_to(runtime / 'backups'):
        raise ValueError('La copia de recuperación no pertenece a esta instalación.')
    paths = targets(runtime, Path(value['vault']).resolve())
    if not set(value['existing']).issubset(paths):
        raise ValueError('La copia contiene destinos no reconocidos.')
    # Read/validate the whole snapshot before touching the current installation.
    if any(not (backup / name).exists() for name in value['existing']):
        raise ValueError('La copia de recuperación está incompleta; se conserva el estado actual.')
    stop_agents()
    for name, target in paths.items():
        if target.is_symlink():
            raise ValueError('No se sustituirá una ruta que cambió a enlace simbólico.')
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink(missing_ok=True)
        if name in value['existing']:
            source = backup / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target, symlinks=True)
            else:
                shutil.copy2(source, target)
    docker = ['docker', '--context', value['context']]
    if value['image']:
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', value['image']):
            raise ValueError('La imagen anterior no tiene una identidad válida.')
        override = backup / 'restore-image.json'
        write_private(override, json.dumps({'services': {'margen': {'image': value['image']}}}))
        compose = [*docker, 'compose', '--project-name', 'prelo', '--project-directory', runtime / 'app',
                   '--env-file', runtime / 'service.env', '--file', runtime / 'app/compose.yaml', '--file', override]
        config = json.loads(run([*compose, 'config', '--format', 'json'], timeout=15).stdout)
        if any(v.get('type') == 'bind' for service in config.get('services', {}).values() for v in service.get('volumes', [])):
            raise ValueError('La configuración anterior contiene bind mounts; no se iniciará.')
        run([*compose, 'up', '-d', '--no-build', '--wait', '--wait-timeout', '120', 'margen'], timeout=180)
        container = run([*compose, 'ps', '-q', 'margen'], timeout=15).stdout.strip()
        if container and (runtime / 'app/dist/margen').is_dir():
            run([*docker, 'cp', str(runtime / 'app/dist/margen') + '/.', container + ':/data/.plugin-release/'], timeout=30)
    else:
        # Failed first installation: stop its own project, but never remove data volumes.
        ids = run([*docker, 'ps', '-q', '--filter', 'label=com.docker.compose.project=prelo'], timeout=15).stdout.split()
        if ids:
            run([*docker, 'stop', *ids], timeout=30)
    for label in LABELS:
        if label in value['existing']:
            load_agent(label, paths[label])
    journal.unlink()
    return backup
