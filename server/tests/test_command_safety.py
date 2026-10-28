"""Command safety uses synthetic inventories and files, never a physical reader."""
import hashlib
import sqlite3
import uuid
import pytest
from margen import kobo, library
from margen.native import Worker


def removal(root):
    library.save_inventory(root, {'device': 'A', 'books': [dict(path='book.epub',title='Book',sha256=hashlib.sha256(b'original').hexdigest())]})
    return kobo.request_removal(root, 'book.epub', 'A')


def test_orders_are_bound_to_device_and_claimed_before_cancelling(tmp_path):
    command = removal(tmp_path)
    assert kobo.pending(tmp_path) == []
    assert kobo.pending(tmp_path, 'B') == []
    with pytest.raises(ValueError): kobo.claim(tmp_path, command['id'], 'B')
    claimed = kobo.claim(tmp_path, command['id'], 'A')
    with pytest.raises(ValueError): kobo.cancel(tmp_path, command['id'])
    assert kobo.claim(tmp_path, command['id'], 'A')['claim_token'] == claimed['claim_token']
    with pytest.raises(ValueError): kobo.complete(tmp_path, command['id'], True)
    kobo.complete(tmp_path, command['id'], True, device='A',claim_token=claimed['claim_token'])
    kobo.complete(tmp_path, command['id'], True, device='A',claim_token=claimed['claim_token'])
    assert kobo.pending(tmp_path, 'A') == []


def test_confirmed_cancellation_cannot_be_claimed(tmp_path):
    command = removal(tmp_path)
    kobo.cancel(tmp_path, command['id'])
    with pytest.raises(ValueError): kobo.claim(tmp_path, command['id'], 'A')
    assert kobo.listing(tmp_path)[0]['state'] == 'cancelled'


def test_worker_preserves_replaced_book_and_wrong_reader(tmp_path):
    root = tmp_path/'service'; root.mkdir()
    command = removal(root)
    mount = tmp_path/'reader'; mount.mkdir(); target=mount/'book.epub'; target.write_bytes(b'replacement')
    worker=Worker({'vault': str(tmp_path), 'state': str(tmp_path/'state')})
    def api(route, body=None, binary=False):
        if route.startswith('/v1/kobo/commands?'): return kobo.pending(root, route.split('=')[1])
        if route.endswith('/claim'): return kobo.claim(root, command['id'], body['device'])
        if route.endswith('/done'): return kobo.complete(root, command['id'], **body)
        return {}
    worker.api=api
    assert worker.carry_out(mount, 'B') == 0
    assert target.read_bytes() == b'replacement'
    worker.carry_out(mount, 'A')
    assert target.read_bytes() == b'replacement'
    assert kobo.listing(root)[0]['state'] == 'failed'


def test_old_commands_are_retained_but_never_auto_executed(tmp_path):
    identity=str(uuid.uuid4())
    with sqlite3.connect(tmp_path/'.library.sqlite') as db:
        db.execute('CREATE TABLE kobo_commands (id TEXT PRIMARY KEY,kind TEXT,path TEXT,title TEXT,sha256 TEXT,state TEXT,message TEXT,created_at TEXT,done_at TEXT)')
        db.execute('INSERT INTO kobo_commands VALUES (?,?,?,?,?,?,?,?,?)',(identity,'remove','book.epub','Book',None,'pending',None,'2026-01-01',None))
    assert kobo.pending(tmp_path,'A') == []
    record=kobo.listing(tmp_path)[0]
    assert record['id']==identity and record['state']=='failed'
