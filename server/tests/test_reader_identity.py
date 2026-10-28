"""Synthetic reader metadata and HTTP service; no hardware or native operations."""
import json
import sqlite3
import uuid
import pytest
from fastapi.testclient import TestClient
from margen import kobo, library, native
from margen.app import app


def test_firmware_update_keeps_pending_orders_on_the_same_reader(tmp_path, monkeypatch):
    root, mount, vault = (tmp_path / name for name in ('service', 'reader', 'vault'))
    vault.mkdir()
    (mount / '.kobo').mkdir(parents=True)
    version = mount / '.kobo/version'
    version.write_text('SYNTHETIC-SERIAL,hardware,4.38.21908,model')
    with sqlite3.connect(mount / '.kobo/KoboReader.sqlite') as db:
        db.executescript("CREATE TABLE content (ContentID TEXT, ContentType INTEGER, Title TEXT);"
                        "CREATE TABLE Bookmark (BookmarkID TEXT, VolumeID TEXT, Text TEXT);"
                        "INSERT INTO content VALUES ('file:///mnt/onboard/book.epub',6,'Book');")
    (mount / 'book.epub').write_bytes(b'synthetic')
    monkeypatch.setenv('MARGEN_DATA', str(root))
    monkeypatch.setenv('MARGEN_TOKEN', 'x'*32)
    client = TestClient(app)
    worker = native.Worker({'vault': str(vault), 'state': str(tmp_path/'state'), 'highlights_folder': 'Quotes', 'auto_eject': False})
    def api(route, body=None, binary=False):
        response = client.request('GET' if body is None else 'POST', route,
                                  headers={'Authorization': 'Bearer '+'x'*32}, json=body)
        response.raise_for_status()
        return response.content if binary else response.json()
    worker.api = api
    worker.synchronize(mount)
    device = library.inventory(root)['device']
    command = kobo.request_removal(root, 'book.epub', device)
    version.write_text('SYNTHETIC-SERIAL,hardware,4.39.23027,model')
    worker.synchronize(mount)
    assert library.inventory(root)['device'] == device
    assert not (mount/'book.epub').exists()
    assert next(c for c in kobo.listing(root) if c['id'] == command['id'])['state'] == 'done'


def test_legacy_firmware_targets_are_failed_without_reassignment(tmp_path):
    with library.database(tmp_path) as db:
        identity = str(uuid.uuid4())
        db.execute('INSERT INTO kobo_commands VALUES (?,?,?,?,?,?,?,?,?)',
                   (identity, 'remove', 'book.epub', 'Book', 'a'*64, 'pending', None, '2026-01-01', None))
        db.execute('INSERT INTO kobo_command_targets(id,device) VALUES (?,?)', (identity, 'a'*20))
    record = kobo.listing(tmp_path)[0]
    assert record['state'] == 'failed'
    assert record['done_at']
    assert 'Vuelve a solicitar' in record['message']
    with library.database(tmp_path) as db:
        assert db.execute('SELECT device FROM kobo_command_targets').fetchone()[0] == 'a'*20
    with pytest.raises(ValueError):
        kobo.claim(tmp_path, identity, 'serial-'+'b'*20)


def test_api_still_rejects_reusing_another_readers_command(tmp_path):
    for device in ['A', 'B']:
        library.save_inventory(tmp_path, {'device': device, 'books': [dict(path='book.epub', title='Book', sha256='a'*64)]})
        if device == 'A':
            first = kobo.request_removal(tmp_path, 'book.epub', device)
        else:
            with pytest.raises(ValueError, match='otro lector'):
                kobo.request_removal(tmp_path, 'book.epub', device)
    assert kobo.pending(tmp_path, 'A')[0]['id'] == first['id']
    assert not kobo.pending(tmp_path, 'B')


def test_missing_serial_never_falls_back_to_mount_identity(tmp_path):
    with pytest.raises(ValueError, match='identificar'):
        native.reader_identity(tmp_path)
    (tmp_path/'.kobo').mkdir()
    (tmp_path/'.kobo/version').write_text(',hardware,4.38,model')
    with pytest.raises(ValueError, match='identificar'):
        native.reader_identity(tmp_path)


def test_overview_exposes_command_target_and_retains_failed_warning(tmp_path):
    library.save_inventory(tmp_path, {'device': 'A', 'books': [dict(path='book.epub', title='Book', sha256='a'*64)]})
    command = kobo.request_removal(tmp_path, 'book.epub', 'A')
    library.save_inventory(tmp_path, {'device': 'B', 'books': []})
    view = kobo.overview(tmp_path)
    assert view['device'] == 'B'
    assert view['commands'][0]['device'] == 'A'
    with library.database(tmp_path) as db:
        db.execute('DELETE FROM kobo_command_targets WHERE id=?', (command['id'],))
    view = kobo.overview(tmp_path)
    assert view['commands'][0]['state'] == 'failed' and view['commands'][0]['done_at']
    library.save_inventory(tmp_path, {'device': 'B', 'books': []})
    assert kobo.overview(tmp_path)['commands'][0]['state'] == 'failed'
    kobo.cancel(tmp_path, command['id'])
    assert kobo.overview(tmp_path)['commands'][0]['state'] == 'cancelled'
