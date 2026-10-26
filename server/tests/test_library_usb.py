import hashlib
import io
import json
import sqlite3
import uuid
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from margen.app import app
from margen import library
from margen.native import Worker, append_notes, read_kobo

TOKEN = "library-test-" + "x" * 32
AUTH = {"Authorization": "Bearer " + TOKEN}
NOTE = {"id": str(uuid.uuid4()), "path": "clases/docker.md", "title": "Docker",
        "markdown": "# Docker\n\nUna imagen es una plantilla.\n", "original_sha256": "a" * 64}


@pytest.fixture
def environment(tmp_path, monkeypatch):
    root = tmp_path / "service"
    monkeypatch.setenv("MARGEN_DATA", str(root))
    monkeypatch.setenv("MARGEN_TOKEN", TOKEN)
    return TestClient(app), root


def publish(client, queued=False, title="Docker"):
    result = client.post("/v1/publications", headers=AUTH,
                         json={"notes": [NOTE], "title": title, "send_to_kobo": queued})
    assert result.status_code == 201, result.text
    return result.json()


def test_shared_identity_adopts_old_editions_and_survives_rename(environment):
    client, root = environment
    publish(client)
    body = {"notes": [{"path": NOTE["path"], "sha256": "a" * 64}]}
    first = client.post("/v1/sources", headers=AUTH, json=body).json()["notes"][0]
    assert first["id"] == NOTE["id"]
    assert client.post("/v1/sources", headers=AUTH, json=body).json()["notes"][0] == first
    moved = {"notes": [{"path": "otra/docker.md", "sha256": "b" * 64, "id": first["id"]}]}
    assert client.post("/v1/sources", headers=AUTH, json=moved).json()["notes"][0]["id"] == first["id"]
    duplicate = {"notes": [moved["notes"][0], {**moved["notes"][0], "path": "otra/copia.md"}]}
    assert client.post("/v1/sources", headers=AUTH, json=duplicate).status_code == 422


def test_retention_keeps_provenance_pinned_and_queued(environment):
    client, root = environment
    old = publish(client, title="Antigua")
    pinned = publish(client, title="Conservada")
    queued = publish(client, queued=True, title="Pendiente")
    client.post(f"/v1/publications/{pinned['id']}/action", headers=AUTH, json={"action": "pin"})
    used = library.storage(root)["used_bytes"]
    old_size = sum(p.stat().st_size for p in (root / old["id"]).iterdir() if p.suffix in {".epub", ".svg"})
    with library.database(root) as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES ('limit_bytes',?)", (str(used - old_size // 2),))
    library.cleanup(root)
    assert not (root / old["id"] / old["filename"]).exists()
    assert (root / pinned["id"] / pinned["filename"]).is_file()
    assert (root / queued["id"] / queued["filename"]).is_file()
    assert client.get(f"/v1/publications/{old['id']}/epub", headers=AUTH).status_code == 410
    result = client.post("/v1/highlights/resolve", headers=AUTH, json={"highlights": [{
        "id": "later", "volume_id": "file:///mnt/onboard/" + old["filename"], "text": "Una imagen es una plantilla."
    }]}).json()["highlights"][0]
    assert result["source"]["id"] == NOTE["id"]
    with library.database(root) as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES ('limit_bytes','1')")
    with pytest.raises(ValueError, match="protegidas"):
        library.cleanup(root)
    assert (root / pinned["id"] / pinned["filename"]).is_file()


def test_delivery_receipt_requires_exact_bytes_and_persists(environment):
    client, root = environment
    record = publish(client, queued=True)
    url = f"/v1/deliveries/{record['id']}/receipt"
    assert client.post(url, headers=AUTH, json={"checksum": "0" * 64, "device": "kobo"}).status_code == 422
    assert len(client.get("/v1/deliveries", headers=AUTH).json()) == 1
    data = (root / record["id"] / record["filename"]).read_bytes()
    assert client.post(url, headers=AUTH, json={"checksum": hashlib.sha256(data).hexdigest(), "device": "kobo"}).status_code == 200
    assert not TestClient(app).get("/v1/deliveries", headers=AUTH).json()


def test_shared_draft_is_visible_to_another_client_and_transfer_is_protected(environment):
    client, root = environment
    identity = str(uuid.uuid4())
    payload = {"id": identity, "title": "Para estudiar", "paths": [NOTE["path"]], "style": "study"}
    assert client.post("/v1/drafts", headers=AUTH, json=payload).status_code == 200
    assert TestClient(app).get("/v1/drafts", headers=AUTH).json()[0]["id"] == identity
    record = publish(client, queued=True)
    claim = f"/v1/deliveries/{record['id']}/claim"
    assert client.post(claim, headers=AUTH, json={"device": "one"}).status_code == 200
    assert client.post(claim, headers=AUTH, json={"device": "two"}).status_code == 422
    assert client.post(f"/v1/publications/{record['id']}/action", headers=AUTH, json={"action": "cancel"}).status_code == 422
    assert client.delete(f"/v1/drafts/{identity}", headers=AUTH).status_code == 200
    assert not TestClient(app).get("/v1/drafts", headers=AUTH).json()


def make_kobo(path, filename):
    (path / ".kobo").mkdir(parents=True)
    db = sqlite3.connect(path / ".kobo/KoboReader.sqlite")
    db.executescript("CREATE TABLE content (ContentID TEXT, ContentType INTEGER, Title TEXT, Attribution TEXT);"
                     "CREATE TABLE Bookmark (BookmarkID TEXT, VolumeID TEXT, ContentID TEXT, Text TEXT, Annotation TEXT, DateCreated TEXT, Hidden TEXT);")
    volume = "file:///mnt/onboard/" + filename
    db.execute("INSERT INTO content VALUES (?,6,'Docker','')", (volume,))
    db.execute("INSERT INTO Bookmark VALUES (?,?,?,?,?,?,?)",
               ("mark-one", volume, "", "Una imagen es una plantilla.", "¡Revisar!", "2026-10-20T12:30:00Z", "false"))
    db.execute("INSERT INTO Bookmark VALUES (?,?,?,?,?,?,?)",
               ("hidden", volume, "", "No importar", "", "", "true"))
    db.commit()
    db.close()


def test_native_usb_roundtrip_retry_and_no_overwrite(environment, tmp_path):
    client, root = environment
    record = publish(client, queued=True)
    mount, vault = tmp_path / "Kobo", tmp_path / "vault"
    (vault / "clases").mkdir(parents=True)
    (vault / NOTE["path"]).write_text(f'---\nmargen_id: {NOTE["id"]}\n---\n{NOTE["markdown"]}')
    make_kobo(mount, record["filename"])
    before = (mount / ".kobo/KoboReader.sqlite").read_bytes()
    worker = Worker({"vault": str(vault), "state": str(tmp_path / "worker"), "highlights_folder": "Subrayados", "auto_eject": False})
    def api(route, body=None, binary=False):
        response = client.get(route, headers=AUTH) if body is None else client.post(route, headers=AUTH, json=body)
        response.raise_for_status()
        return response.content if binary else response.json()
    worker.api = api
    assert worker.synchronize(mount)["added"] == 1
    imported = next((vault / "Subrayados").glob("*.md"))
    original = imported.read_text()
    assert "Fecha : 20/10/2026" in original and "[[clases/docker]]" in original
    assert "No importar" not in original
    imported.write_text(original + "\nMi comentario personal.\n")
    assert worker.synchronize(mount)["added"] == 0
    assert imported.read_text() == original + "\nMi comentario personal.\n"
    assert (mount / ".kobo/KoboReader.sqlite").read_bytes() == before
    assert (mount / record["filename"]).read_bytes() == (root / record["id"] / record["filename"]).read_bytes()
    client.post(f"/v1/publications/{record['id']}/action", headers=AUTH, json={"action": "queue"})
    (mount / record["filename"]).write_bytes(b"otra copia que debe conservarse")
    with pytest.raises(ValueError, match="contenido distinto"):
        worker.synchronize(mount)
    assert (mount / record["filename"]).read_bytes() == b"otra copia que debe conservarse"
    assert len(api("/v1/deliveries")) == 1


def test_kobo_pending_wal_is_never_imported(tmp_path):
    make_kobo(tmp_path / "Kobo", "book.epub")
    (tmp_path / "Kobo/.kobo/KoboReader.sqlite-wal").write_bytes(b"pending")
    with pytest.raises(ValueError, match="cambios pendientes"):
        read_kobo(tmp_path / "Kobo")


def test_backup_restore_keeps_archived_source_mapping(environment, tmp_path):
    client, root = environment
    old = publish(client)
    kept = publish(client, queued=True)
    (root / old["id"] / old["filename"]).unlink()
    result = client.get("/v1/backup", headers=AUTH)
    assert result.status_code == 200
    restored = tmp_path / "restored"
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert kept["id"] + "/" + kept["filename"] in archive.namelist()
        assert old["id"] + "/manifest.json" in archive.namelist()
    import importlib.util
    spec = importlib.util.spec_from_file_location("margen_restore", Path(__file__).resolve().parents[2] / "scripts/restore_backup.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    export = tmp_path / "export.zip"
    export.write_bytes(result.content)
    assert module.restore(export, restored)["editions"] == 2
    with pytest.raises(ValueError, match="ya existe"):
        module.restore(export, restored)
    rows = library.records(restored)
    assert next(r for r in rows if r["id"] == kept["id"])["delivery"] == "queued"
    assert next(r for r in rows if r["id"] == old["id"])["sources"][0]["id"] == NOTE["id"]


def test_private_installation_package_works_with_three_file_plugin(environment, monkeypatch):
    client, root = environment
    monkeypatch.setenv('MARGEN_PUBLIC_URL', 'https://reader.example.test')
    release = root / '.plugin-release'
    release.mkdir(parents=True)
    for name in ['main.js', 'manifest.json', 'styles.css']:
        (release / name).write_text('{}' if name == 'manifest.json' else '/* synthetic */')
    assert client.get('/v1/installation/package').status_code == 401
    result = client.get('/v1/installation/package', headers=AUTH)
    assert result.status_code == 200
    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert 'margen/main.js' in archive.namelist()
        assert 'margen/sql-wasm.wasm' not in archive.namelist()
        connection = json.loads(archive.read('conexion-prelo.json'))
        assert connection['token'] == TOKEN
        assert connection['serverUrl'] == 'https://reader.example.test'
        assert connection['highlightsFolder'] == 'Prelo/Subrayados'


@pytest.mark.parametrize("queued,pinned", [(False, False), (True, False), (False, True)])
def test_delete_epub_retires_files_and_queue_but_preserves_annotations(environment, queued, pinned):
    client, root = environment
    record = publish(client, queued=queued)
    other = publish(client, title="Otra edición")
    endpoint = f"/v1/publications/{record['id']}/action"
    if pinned:
        assert client.post(endpoint, headers=AUTH, json={"action": "pin"}).status_code == 200
    assert client.post(endpoint, json={"action": "delete"}).status_code == 401
    assert (root / record["id"] / record["filename"]).exists()
    highlight = {"id": "saved", "volume_id": record["filename"], "text": "Una imagen es una plantilla."}
    assert client.post("/v1/annotations", headers=AUTH, json={"highlights": [highlight]}).status_code == 200
    for _ in range(2):  # Repeated deletion is harmless.
        result = client.post(endpoint, headers=AUTH, json={"action": "delete"})
        assert result.status_code == 200, result.text
        deleted = result.json()
        assert not deleted["available"] and not deleted["pinned"]
        assert deleted["delivery"] == "none" and deleted["archived_at"]
    assert not (root / record["id"] / record["filename"]).exists()
    assert not (root / record["id"] / "cover.svg").exists()
    assert (root / record["id"] / "manifest.json").exists()
    assert (root / other["id"] / other["filename"]).exists()
    assert client.get(f"/v1/publications/{record['id']}/epub", headers=AUTH).status_code == 410
    assert not client.get("/v1/deliveries", headers=AUTH).json()
    assert client.post(endpoint, headers=AUTH, json={"action": "queue"}).status_code == 422
    resolved = client.post("/v1/highlights/resolve", headers=AUTH, json={"highlights": [highlight]}).json()["highlights"][0]
    assert resolved["source"]["id"] == NOTE["id"]
    with library.database(root) as db:
        assert db.execute("SELECT count(*) FROM annotations").fetchone()[0] == 1


def test_delete_cannot_interrupt_active_usb_transfer(environment):
    client, root = environment
    record = publish(client, queued=True)
    assert client.post(f"/v1/deliveries/{record['id']}/claim", headers=AUTH, json={"device": "kobo"}).status_code == 200
    result = client.post(f"/v1/publications/{record['id']}/action", headers=AUTH, json={"action": "delete"})
    assert result.status_code == 422
    assert (root / record["id"] / record["filename"]).exists()
    assert client.get("/v1/deliveries", headers=AUTH).json()[0]["delivery"] == "transferring"


def test_kobo_opaque_text_columns_are_not_decoded(tmp_path):
    mount = tmp_path / "reader"
    make_kobo(mount, "margen-test.epub")
    path = mount / ".kobo/KoboReader.sqlite"
    with sqlite3.connect(path) as db:
        for table in ["Bookmark", "content"]:
            db.execute(f"ALTER TABLE {table} ADD COLUMN ExtraAnnotationData TEXT")
            db.execute(f"UPDATE {table} SET ExtraAnnotationData=CAST(X'FFFE80' AS TEXT)")
    before = path.read_bytes()
    rows = read_kobo(mount)
    assert len(rows) == 1
    assert rows[0]["text"] == "Una imagen es una plantilla."
    assert path.read_bytes() == before


def test_library_reports_where_each_delivery_really_is(environment, tmp_path):
    client, root = environment
    vault, mount = tmp_path / "vault", tmp_path / "KOBOeReader"
    vault.mkdir()
    make_kobo(mount, "otro-libro.epub")
    worker = Worker({"vault": str(vault), "state": str(tmp_path / "worker"), "highlights_folder": "Subrayados", "auto_eject": False})
    def api(route, body=None, binary=False):
        response = client.get(route, headers=AUTH) if body is None else client.post(route, headers=AUTH, json=body)
        response.raise_for_status()
        return response.content if binary else response.json()
    worker.api = api
    state = lambda record: next(p for p in api("/v1/library")["publications"] if p["id"] == record["id"])["on_kobo"]
    first, second = publish(client, queued=True, title="Primera"), publish(client, queued=True, title="Segunda")
    worker.synchronize(mount)
    assert state(first) == state(second) == "copied"
    # After disconnecting, the reader imported only the first one and the reader opened it.
    with sqlite3.connect(mount / ".kobo/KoboReader.sqlite") as db:
        db.execute("ALTER TABLE content ADD COLUMN ___PercentRead INTEGER")
        db.execute("INSERT INTO content VALUES (?,6,'Primera','Prelo',35)", ("file:///mnt/onboard/" + first["filename"],))
    worker.synchronize(mount)
    library_state = api("/v1/library")
    assert state(first) == "imported" and state(second) == "not_imported"
    assert next(p for p in library_state["publications"] if p["id"] == first["id"])["percent_read"] == 35
    assert {b["title"] for b in library_state["kobo"]["books"]} == {"Docker", "Primera"}
    (mount / second["filename"]).unlink()
    worker.synchronize(mount)
    assert state(second) == "missing"
