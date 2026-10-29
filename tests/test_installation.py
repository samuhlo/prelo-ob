"""Synthetic installer checks. These do not validate a physical Kobo or launchd."""
import importlib
import json
import os
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from install_common import relative_folder, validate_connection
from install_plugin import install as plugin_install
import install as installer
import install_usb


@pytest.fixture
def fixture(tmp_path):
    root = tmp_path / 'Downloaded app with spaces'
    source = root / 'dist/margen'; source.mkdir(parents=True)
    (source / 'manifest.json').write_text(json.dumps({'id': 'margen', 'version': '0.7.0'}))
    (source / 'main.js').write_text('/* built fixture */')
    (source / 'styles.css').write_text('/* style fixture */')
    vault = tmp_path / 'My vault'; (vault / '.obsidian').mkdir(parents=True)
    return root, vault


def test_plugin_install_and_update_preserve_state_and_other_plugins(fixture):
    root, vault = fixture
    enabled = vault / '.obsidian/community-plugins.json'; enabled.write_text('["another-plugin"]')
    connection = {'serverUrl': 'https://reader.example.test', 'token': 'synthetic-' + 'x' * 32,
                  'highlightsFolder': 'Reading/Highlights'}
    target = plugin_install(vault, root=root, connection=connection, enable=True)
    state = json.loads((target / 'data.json').read_text(encoding="utf-8-sig"))
    state['composer'] = {'paths': ['kept.md'], 'step': 2}
    (target / 'data.json').write_text(json.dumps(state))
    before = (target / 'data.json').read_bytes()
    (root / 'dist/margen/main.js').write_text('/* upgraded fixture */')
    plugin_install(vault, root=root, enable=True)
    assert (target / 'data.json').read_bytes() == before
    assert json.loads(enabled.read_text(encoding="utf-8-sig")) == ['another-plugin', 'margen']
    assert (target / 'main.js').read_text(encoding="utf-8-sig") == '/* upgraded fixture */'
    assert list((root / 'data/plugin-backups').glob('*/margen/data.json'))
    assert not (target / 'sql-wasm.wasm').exists()
    if os.name != 'nt':
        assert (target / 'data.json').stat().st_mode & 0o077 == 0


def test_invalid_connection_does_not_write_plugin(fixture):
    root, vault = fixture
    with pytest.raises(ValueError):
        plugin_install(vault, root=root, connection={'serverUrl': 'file:///etc/passwd', 'token': 'x' * 32})
    assert not (vault / '.obsidian/plugins/margen').exists()
    with pytest.raises(ValueError):
        validate_connection({'serverUrl': 'https://user:password@example.test', 'token': 'x' * 32})
    for value in ['../escape', '/absolute', '.obsidian', 'C:\\Users\\someone']:
        with pytest.raises(ValueError):
            relative_folder(value)


def test_first_service_install_refuses_an_occupied_port(fixture, tmp_path, monkeypatch):
    root, _ = fixture
    monkeypatch.setattr(installer.sys, 'platform', 'darwin')
    monkeypatch.setattr(installer.shutil, 'which', lambda name: '/bin/' + name)
    monkeypatch.setattr(installer, 'occupied', lambda port: True)
    calls = []
    monkeypatch.setattr(installer, 'run', lambda *a, **k: calls.append(a))
    with pytest.raises(ValueError, match='ocupado'):
        installer.preflight(tmp_path / 'New runtime', 'none', root)
    assert calls == []
    assert not (tmp_path / 'New runtime').exists()


def test_usb_install_requires_explicit_vault(tmp_path, monkeypatch):
    runtime = tmp_path / 'runtime'
    python = runtime / 'server/.venv/bin/python'; python.parent.mkdir(parents=True); python.touch()
    env = tmp_path / 'private.env'; env.write_text('MARGEN_TOKEN=' + 'x' * 32)
    monkeypatch.setattr(install_usb.sys, 'platform', 'darwin')
    with pytest.raises(ValueError, match='--vault'):
        install_usb.install(runtime, env)
    assert not (runtime / 'usb.json').exists()


def test_usb_config_preserves_existing_vault_and_writes_bounded_login_agent(fixture, tmp_path, monkeypatch):
    _, vault = fixture
    runtime = tmp_path / 'Library/Application Support/Prelo'
    python = runtime / 'server/.venv/bin/python'; python.parent.mkdir(parents=True); python.touch()
    env = tmp_path / 'private.env'; env.write_text('MARGEN_TOKEN=' + 'x' * 32)
    (runtime / 'usb.json').write_text(json.dumps({'vault': str(vault), 'highlights_folder': 'Existing/Quotes', 'auto_eject': False}))
    monkeypatch.setattr(install_usb.sys, 'platform', 'darwin')
    monkeypatch.setattr(install_usb.Path, 'home', classmethod(lambda cls: tmp_path))
    agents = []
    monkeypatch.setattr(install_usb, 'load_agent', lambda label, path: agents.append((label, path)))
    install_usb.install(runtime, env, label='local.prelo.kobo')
    result = json.loads((runtime / 'usb.json').read_text(encoding="utf-8-sig"))
    assert result['vault'] == str(vault)
    assert result['highlights_folder'] == 'Existing/Quotes'
    assert result['auto_eject'] is False
    assert agents[0][0] == 'local.prelo.kobo'
    assert agents[0][1].is_file()
    assert 'update_command' not in result
    install_usb.install(runtime, env, label='local.prelo.kobo', update_command=['uv', 'run', '{release}/scripts/install.py'])
    install_usb.install(runtime, env, label='local.prelo.kobo')
    assert json.loads((runtime / 'usb.json').read_text())['update_command'] == ['uv', 'run', '{release}/scripts/install.py']


def test_check_only_does_not_create_runtime_or_start_services(fixture, tmp_path, monkeypatch):
    root, vault = fixture
    (root / 'manifest.json').write_text((root / 'dist/margen/manifest.json').read_text(encoding="utf-8-sig"))
    runtime = tmp_path / 'runtime'
    monkeypatch.setattr(installer, 'preflight', lambda *args: 'synthetic-context')
    def unexpected(*args, **kwargs):
        raise AssertionError('A check must not install anything')
    monkeypatch.setattr(installer, 'install_bridge', unexpected)
    monkeypatch.setattr(installer, 'install_usb', unexpected)
    installer.install_service(vault, root=root, runtime=runtime, check=True)
    assert not runtime.exists()


def test_connection_cli_accepts_utf8_with_bom(fixture, tmp_path, monkeypatch, capsys):
    import install_plugin
    _, vault = fixture
    connection = {'serverUrl': 'https://reader.example.test', 'token': 'synthetic-' + 'x' * 32,
                  'highlightsFolder': 'Lecturas/Anotación 日本語'}
    config = tmp_path / 'conexion.json'
    config.write_text(json.dumps(connection, ensure_ascii=False), encoding='utf-8-sig')
    received = []
    monkeypatch.setattr(sys, 'argv', ['install_plugin.py', str(vault), '--connection', str(config)])
    monkeypatch.setattr(install_plugin, 'install', lambda vault, **kwargs: received.append(kwargs) or vault)
    install_plugin.main()
    assert received[0]['connection']['highlightsFolder'] == connection['highlightsFolder']
    assert connection['token'] not in capsys.readouterr().out


def test_build_context_files_get_fresh_timestamps(tmp_path):
    # Two releases with a same-length edit must not reuse the cached file.
    source = tmp_path / "server/margen/__init__.py"
    source.parent.mkdir(parents=True)
    source.write_text('__version__ = "0.9.2"\n')
    os.utime(source, (1767225600, 1767225600))
    installer.fresh_build_context(tmp_path / "server")
    assert source.stat().st_mtime > 1767225600


def test_manual_install_supersedes_pending_auto_update(fixture):
    import hashlib
    root, vault = fixture
    target = plugin_install(vault, root=root)
    pending = target / '.prelo-update'
    pending.mkdir(exist_ok=True)
    names = ['main.js', 'styles.css', 'manifest.json']
    for name in names:
        (pending/name).write_bytes((target/name).read_bytes())
    expected = {name: hashlib.sha256((target/name).read_bytes()).hexdigest() for name in names}
    (pending/'pending.json').write_text(json.dumps(expected))
    (root/'dist/margen/main.js').write_text('/* later manual version */')
    plugin_install(vault, root=root)
    assert (target/'main.js').read_text() == '/* later manual version */'
    assert not (pending/'pending.json').exists(), 'An abandoned auto-update would undo this manual installation on startup'


@pytest.mark.parametrize('interrupted_restore', [False, True])
def test_partial_manual_install_recovers_without_losing_auto_journal(fixture, monkeypatch, interrupted_restore):
    import install_plugin
    root, vault = fixture
    target = plugin_install(vault, root=root)
    before = {name: (target/name).read_bytes() for name in install_plugin.PLUGIN_FILES}
    (root/'dist/margen/main.js').write_text('/* manual new entry */')
    writer = install_plugin.write_private
    failed = False
    def fail(path, content, **kwargs):
        nonlocal failed
        if path == target/'styles.css' and (not failed or interrupted_restore):
            failed = True
            raise OSError('Synthetic manual write failure')
        return writer(path, content, **kwargs)
    monkeypatch.setattr(install_plugin, 'write_private', fail)
    with pytest.raises(OSError, match='Synthetic'):
        plugin_install(vault, root=root)
    monkeypatch.setattr(install_plugin, 'write_private', writer)
    if interrupted_restore:
        assert (target/'.prelo-update/pending.json').exists()
        assert (target/'main.js').read_text() == '/* manual new entry */'
        install_plugin.recover_plugin_update(target)
    for name, content in before.items():
        assert (target/name).read_bytes() == content
    assert not (target/'.prelo-update/pending.json').exists()
