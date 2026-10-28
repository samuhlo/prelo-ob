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
    # Native flock is exercised separately on POSIX; desktop fixture runs on Windows too.
    if sys.platform == 'win32':
        from contextlib import nullcontext
        monkeypatch.setattr(installer, 'usb_update_guard', lambda runtime: nullcontext())
    home=tmp_path/'home';home.mkdir()
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:home))
    monkeypatch.setattr(install_usb.sys,'platform','darwin')
    monkeypatch.setattr(transaction.os,'getuid',lambda:501,raising=False)
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


def test_failed_first_install_can_be_retried(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: home))
    monkeypatch.setattr(transaction.os, 'getuid', lambda: 501, raising=False)
    monkeypatch.setattr(installer.sys, 'platform', 'darwin')
    monkeypatch.setattr(installer.shutil, 'which', lambda name: '/bin/' + name)
    monkeypatch.setattr(installer, 'occupied', lambda port: False)
    root = tmp_path / 'release'
    plugin = root / 'dist/margen'
    plugin.mkdir(parents=True)
    for name in installer.PLUGIN_FILES:
        (plugin / name).write_text('synthetic')
    vault = tmp_path / 'vault'
    (vault / '.obsidian').mkdir(parents=True)
    runtime = tmp_path / 'runtime'
    docker = {'exists': False, 'running': False}

    def run(args, **kwargs):
        args = list(map(str, args))
        output = ''
        if args[:3] == ['docker', 'context', 'show']:
            output = 'fixture'
        elif 'ps' in args:
            present = docker['exists'] if '-aq' in args else docker['running']
            output = docker.get('id', 'failed-container') if present else ''
        elif 'inspect' in args:
            output = json.dumps([{'Mounts': [], 'Config': {'Labels': {'com.docker.compose.project.working_dir': str((runtime/'app').resolve())}}}])
        elif 'stop' in args:
            docker['running'] = False
        elif 'rm' in args or 'down' in args:
            docker.update(exists=False, running=False)
        return SimpleNamespace(stdout=output, returncode=0)

    monkeypatch.setattr(installer, 'run', run)
    monkeypatch.setattr(transaction, 'run', run)
    transaction.capture(runtime, vault, 'fixture', '')
    (runtime / 'app').mkdir()
    (runtime / 'installation.json').write_text(json.dumps({'docker_context': 'fixture', 'state': 'installing'}))
    (runtime / 'service.env').write_text('MARGEN_TOKEN=' + 'x' * 32)
    docker.update(exists=True, running=True)
    assert installer.preflight(runtime, 'none', root) == 'fixture'
    transaction.recover(runtime)
    error = None
    try:
        installer.preflight(runtime, 'none', root)
    except ValueError as exc:
        error = str(exc)
    assert error is None, f'La recuperación impide reintentar la instalación: {error}'
    marker = json.loads((runtime/'installation.json').read_text())
    assert marker['state'] == 'retry' and marker['retry_containers'] == ['failed-container']
    assert not docker['running'] and docker['exists']
    docker['id'] = 'foreign-container'
    with pytest.raises(ValueError, match='ajenos'):
        installer.preflight(runtime, 'none', root)


def test_update_accepts_existing_utf8_bom_plugin_settings(setup):
    root, vault, runtime, calls, failure = setup
    state = vault / '.obsidian/plugins/margen/data.json'
    state.write_bytes(b'\xef\xbb\xbf' + state.read_bytes())
    installer.install_service(vault, root=root, runtime=runtime, ai='none')


@pytest.mark.parametrize('heartbeat,allowed', [('2000-01-01T00:00:00+00:00', True), ('recent', False), ('invalid', False)])
def test_usb_heartbeat_distinguishes_stale_and_live_work(setup, monkeypatch, heartbeat, allowed):
    from datetime import datetime, timezone
    root, vault, runtime, calls, _ = setup
    if heartbeat == 'recent':
        heartbeat = datetime.now(timezone.utc).isoformat()
    monkeypatch.setattr(installer, 'request', lambda *args: {'jobs': [], 'device': {'state': 'working', 'heartbeat_at': heartbeat}})
    if allowed:
        installer.install_service(vault, root=root, runtime=runtime, ai='none')
        assert any('up' in args for args in calls)
    else:
        with pytest.raises(ValueError, match='Espera'):
            installer.install_service(vault, root=root, runtime=runtime, ai='none')
        assert not calls


@pytest.mark.skipif(sys.platform == 'win32', reason='macOS connector uses POSIX flock')
def test_stale_heartbeat_with_held_usb_lock_still_blocks_update(setup, monkeypatch):
    import fcntl
    root, vault, runtime, calls, _ = setup
    state = runtime/'custom-state'
    state.mkdir()
    config = json.loads((runtime/'usb.json').read_text())
    (runtime/'usb.json').write_text(json.dumps({**config, 'state': str(state)}))
    monkeypatch.setattr(installer, 'request', lambda *args: {'jobs': [], 'device': {'state': 'working', 'heartbeat_at': '2000-01-01T00:00:00+00:00'}})
    with (state/'usb.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match='copia USB'):
            installer.install_service(vault, root=root, runtime=runtime, ai='none')
    assert not calls and not (runtime/'update-in-progress.json').exists()


@pytest.mark.skipif(sys.platform == 'win32', reason='macOS connector uses POSIX flock')
def test_update_holds_usb_lock_until_installation_finishes(setup, monkeypatch):
    import fcntl
    root, vault, runtime, _, _ = setup
    def install(*args, **kwargs):
        with (runtime/'usb-state/usb.lock').open('a') as lock:
            with pytest.raises(BlockingIOError):
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    monkeypatch.setattr(installer, '_install_service', install)
    installer.install_service(vault, root=root, runtime=runtime, ai='none')
    with installer.usb_update_guard(runtime):
        pass
