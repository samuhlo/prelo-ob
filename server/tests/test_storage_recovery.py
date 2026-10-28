import importlib.util
import io
import os
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from margen.app import app
from margen import kobo, library

TOKEN='synthetic-'+'x'*32
AUTH={'Authorization':'Bearer '+TOKEN}
@pytest.fixture
def service(tmp_path, monkeypatch):
    root=tmp_path/'data';root.mkdir()
    monkeypatch.setenv('MARGEN_DATA',str(root));monkeypatch.setenv('MARGEN_TOKEN',TOKEN)
    library.save_inventory(root,{'device':'A','books':[]})
    return TestClient(app),root


def epub(size=0):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w') as archive:
        archive.writestr('mimetype','application/epub+zip')
        archive.writestr('META-INF/container.xml','<container/>')
        archive.writestr('padding',b'x'*size)
    return buf.getvalue()


def test_upload_exceeding_old_body_limit_and_chunked_limit(service, monkeypatch):
    client,root=service
    response=client.post('/v1/kobo/uploads?device=A&filename=large.epub',headers=AUTH,content=epub(37_000_000))
    assert response.status_code==200
    assert kobo.upload_file(root,response.json()['id']).stat().st_size>36_000_000
    monkeypatch.setattr(kobo,'MAX_UPLOAD',1000)
    response=client.post('/v1/kobo/uploads?device=A&filename=too-large.epub',headers=AUTH,content=iter([b'x'*600,b'y'*600]))
    assert response.status_code==413
    assert not list(root.glob('.uploading-*'))


def test_pending_upload_survives_backup_restore(service,tmp_path):
    _,root=service
    command=kobo.upload(root,'book.epub',epub(), 'A')
    backup=library.backup(root)
    spec=importlib.util.spec_from_file_location('restore',Path(__file__).resolve().parents[2]/'scripts/restore_backup.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    try:
        restored=tmp_path/'restored';module.restore(backup,restored)
        assert kobo.upload_file(restored,command['id']).read_bytes()==epub()
        assert kobo.pending(restored,'A')[0]['id']==command['id']
    finally: backup.unlink()


def test_rejected_upload_does_not_leave_an_orphan(service):
    _,root=service
    with library.database(root) as db:db.execute("INSERT OR REPLACE INTO settings VALUES ('limit_bytes','10')")
    with pytest.raises(ValueError,match='cuota'):kobo.upload(root,'book.epub',epub(),'A')
    assert not list((root/'.uploads').glob('*'))


def test_impossible_cleanup_preserves_old_book_and_cache(service):
    client,root=service
    response=client.post('/v1/publications',headers=AUTH,json={'notes':[{'id':'a','title':'Test','path':'a.md','markdown':'Synthetic.'}]})
    assert response.status_code==201
    record=response.json();book=root/record['id']/record['filename'];original=book.read_bytes()
    cache=root/'.art-cache';cache.mkdir();(cache/'art.jpg').write_bytes(b'cache')
    staging=root/'.building-synthetic';staging.mkdir();(staging/'huge.epub').write_bytes(b'x'*10000)
    with library.database(root) as db:db.execute("INSERT OR REPLACE INTO settings VALUES ('limit_bytes','100')")
    with pytest.raises(ValueError):library.cleanup(root)
    assert book.read_bytes()==original and (cache/'art.jpg').read_bytes()==b'cache'


def test_staged_upload_only_reserves_remaining_disk_space(service, monkeypatch):
    import shutil
    client, root = service
    data = epub(2_000_000)
    initial_free = 128_000_000 + len(data) + 1
    usage_type = type(shutil.disk_usage(root))
    def usage(path):
        occupied = sum(p.stat().st_size for p in root.rglob('*')
                       if p.is_file() and p.suffix in {'.partial', '.epub'})
        return usage_type(1_000_000_000, 1_000_000_000 - initial_free + occupied, initial_free - occupied)
    monkeypatch.setattr(shutil, 'disk_usage', usage)
    response = client.post('/v1/kobo/uploads?device=A&filename=book.epub', headers=AUTH, content=data)
    assert response.status_code == 200, response.text
    assert kobo.upload_file(root, response.json()['id']).read_bytes() == data
    assert usage(root).free >= 128_000_000
