"""Shared catalogue, source identities, delivery receipts and bounded binary storage."""
import hashlib
import json
import shutil
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

LOCK = threading.RLock()


def now():
    return datetime.now(timezone.utc).isoformat()


def edition(value):
    if str(uuid.UUID(value)) != value:
        raise ValueError("Identificador de edición no válido.")
    return value


@contextmanager
def database(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with LOCK:
        db = sqlite3.connect(root / ".library.sqlite", timeout=20)
        db.row_factory = sqlite3.Row
        db.executescript("""
            CREATE TABLE IF NOT EXISTS editions (
                id TEXT PRIMARY KEY, pinned INTEGER NOT NULL DEFAULT 0,
                delivery TEXT NOT NULL DEFAULT 'none', queued_at TEXT,
                delivered_at TEXT, device TEXT, checksum TEXT, archived_at TEXT
            );
            CREATE TABLE IF NOT EXISTS sources (
                id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, hash TEXT, updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, at TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS annotations (
                key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS drafts (
                id TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS kobo_commands (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, path TEXT NOT NULL, title TEXT NOT NULL,
                sha256 TEXT, state TEXT NOT NULL, message TEXT, created_at TEXT NOT NULL, done_at TEXT
            );
        """)
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()


def records(root):
    with database(root) as db:
        result = []
        for path in Path(root).glob("*/manifest.json"):
            if path.parent.name.startswith("."):
                continue
            record = json.loads(path.read_text())
            edition(record["id"])
            db.execute("INSERT OR IGNORE INTO editions(id) VALUES (?)", (record["id"],))
            state = dict(db.execute("SELECT * FROM editions WHERE id=?", (record["id"],)).fetchone())
            book = path.parent / record["filename"]
            record.update(state, available=book.is_file(), bytes=book.stat().st_size if book.is_file() else 0)
            for source in record["sources"]:
                db.execute("INSERT OR IGNORE INTO sources VALUES (?,?,?,?)",
                           (source["id"], source["path"], source["sha256"], record["created_at"]))
            result.append(record)
        return sorted(result, key=lambda r: r["created_at"], reverse=True)


def source_ids(root, items):
    records(root)  # Adopt identities of editions created before the shared catalogue.
    with database(root) as db:
        result, used = [], set()
        for item in items:
            path = item["path"].replace("\\", "/")
            if path.startswith("/") or any(p in {"", ".", ".."} for p in path.split("/")):
                raise ValueError("La nota debe tener una ruta relativa dentro del vault.")
            requested = item.get("id")
            if requested:
                edition(requested)
            by_path = db.execute("SELECT * FROM sources WHERE path=?", (path,)).fetchone()
            by_id = db.execute("SELECT * FROM sources WHERE id=?", (requested,)).fetchone() if requested else None
            if by_path and by_id and by_path["id"] != by_id["id"]:
                raise ValueError("La identidad de esta nota entra en conflicto con otra ruta. Revisa sus propiedades.")
            identity = by_id["id"] if by_id else by_path["id"] if by_path else requested or str(uuid.uuid4())
            if identity in used:
                raise ValueError("Dos notas seleccionadas tienen el mismo margen_id. Conserva un identificador distinto para cada nota.")
            used.add(identity)
            db.execute("INSERT INTO sources VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET path=excluded.path, hash=excluded.hash, updated_at=excluded.updated_at",
                       (identity, path, item["sha256"], now()))
            result.append({"id": identity, "path": path})
        return result


def event(db, kind, data):
    db.execute("INSERT INTO events(at,kind,data) VALUES (?,?,?)", (now(), kind, json.dumps(data, ensure_ascii=False)))


def change(root, identity, action):
    edition(identity)
    current = next((r for r in records(root) if r["id"] == identity), None)
    if current is None:
        raise ValueError("Edición no encontrada.")
    with database(root) as db:
        if action in {"queue", "pin"} and not current["available"]:
            raise ValueError("El archivo de esta edición se retiró para liberar espacio.")
        if current["delivery"] == "transferring" and action in {"queue", "cancel", "delete"}:
            started = datetime.fromisoformat(current["queued_at"])
            if (datetime.now(timezone.utc) - started).total_seconds() < 300:
                raise ValueError("Esta edición se está copiando. Espera a que termine o a que caduque el intento.")
        if action == "queue":
            db.execute("UPDATE editions SET delivery='queued',queued_at=? WHERE id=?", (now(), identity))
        elif action == "cancel":
            db.execute("UPDATE editions SET delivery='none' WHERE id=?", (identity,))
        elif action == "delete":
            # Retain provenance so annotations from a Kobo copy still resolve.
            folder = Path(root) / identity
            for name in (f"margen-{identity}.epub", "cover.svg"):
                (folder / name).unlink(missing_ok=True)
            db.execute("UPDATE editions SET delivery='none',queued_at=NULL,pinned=0,archived_at=COALESCE(archived_at,?) WHERE id=?",
                       (now(), identity))
        elif action in {"pin", "unpin"}:
            db.execute("UPDATE editions SET pinned=? WHERE id=?", (action == "pin", identity))
        else:
            raise ValueError("Acción no válida.")
        event(db, action, {"edition": identity})
    return next(r for r in records(root) if r["id"] == identity)


def receipt(root, identity, checksum, device):
    edition(identity)
    book = Path(root) / identity / f"margen-{identity}.epub"
    if not book.is_file() or hashlib.sha256(book.read_bytes()).hexdigest() != checksum:
        raise ValueError("La copia recibida no coincide con la edición del servidor.")
    with database(root) as db:
        db.execute("UPDATE editions SET delivery='sent',delivered_at=?,device=?,checksum=? WHERE id=?",
                   (now(), device, checksum, identity))
        event(db, "delivered", {"edition": identity, "device": device})


def claim(root, identity, device):
    edition(identity)
    with database(root) as db:
        row = db.execute("SELECT * FROM editions WHERE id=?", (identity,)).fetchone()
        if row is None or row["delivery"] not in {"queued", "transferring"}:
            raise ValueError("Esta edición ya no está pendiente.")
        if row["delivery"] == "transferring" and row["device"] != device:
            if (datetime.now(timezone.utc) - datetime.fromisoformat(row["queued_at"])).total_seconds() < 300:
                raise ValueError("Otro lector está recibiendo esta edición.")
        db.execute("UPDATE editions SET delivery='transferring',queued_at=?,device=? WHERE id=?", (now(), device, identity))


def binary_files(root):
    root = Path(root)
    for path in root.rglob("*"):
        if path.is_file() and (path.suffix in {".epub", ".svg", ".jpg", ".png"} or ".art-cache" in path.parts):
            yield path


def storage(root):
    with database(root) as db:
        row = db.execute("SELECT value FROM settings WHERE key='limit_bytes'").fetchone()
        limit = int(row[0]) if row else 10_000_000_000
    used = sum(p.stat().st_size for p in binary_files(root))
    cache = sum(p.stat().st_size for p in (Path(root) / ".art-cache").glob("*") if p.is_file())
    return {"used_bytes": used, "limit_bytes": limit, "cache_bytes": cache,
            "free_disk_bytes": shutil.disk_usage(root).free}


def cleanup(root, incoming=0, protected=(), force=False):
    """Retire binaries only; provenance survives indefinitely. Caller holds LOCK."""
    with LOCK:
        state = storage(root)
        if incoming > state["limit_bytes"]:
            raise ValueError("Esta edición supera por sí sola el límite de biblioteca.")
        if state["used_bytes"] + incoming <= state["limit_bytes"] and not force:
            return {"removed": [], **state}
        target = min(int(state["limit_bytes"] * .9), state["limit_bytes"] - incoming)
        for cache in (Path(root) / ".art-cache", Path(root) / ".ai-cache"):
            if cache.is_dir():
                for p in cache.iterdir():
                    if p.is_file():
                        p.unlink()
        removed = []
        for record in reversed(records(root)):
            if storage(root)["used_bytes"] <= target:
                break
            if record["id"] in protected or record["pinned"] or record["delivery"] in {"queued", "transferring"} or not record["available"]:
                continue
            folder = Path(root) / record["id"]
            # Never remove manifest.json: it is required to resolve future highlights.
            for name in (record["filename"], "cover.svg"):
                (folder / name).unlink(missing_ok=True)
            with database(root) as db:
                db.execute("UPDATE editions SET archived_at=? WHERE id=?", (now(), record["id"]))
            removed.append(record["id"])
        if removed:
            with database(root) as db:
                event(db, "retention", {"editions": removed})
        final = storage(root)
        if final["used_bytes"] + incoming > final["limit_bytes"]:
            raise ValueError("No hay espacio sin retirar ediciones protegidas o pendientes. Amplía el límite o libera alguna.")
        return {"removed": removed, **final}


def set_limit(root, gigabytes):
    if not 1 <= gigabytes <= 1000:
        raise ValueError("El límite debe estar entre 1 y 1000 GB.")
    with database(root) as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES ('limit_bytes',?)", (str(int(gigabytes * 1_000_000_000)),))
        event(db, "limit", {"gb": gigabytes})
    return cleanup(root)


def device_state(root, payload=None):
    with database(root) as db:
        if payload is not None:
            payload = {**payload, "heartbeat_at": now()}
            db.execute("INSERT OR REPLACE INTO settings VALUES ('device',?)", (json.dumps(payload, ensure_ascii=False),))
        row = db.execute("SELECT value FROM settings WHERE key='device'").fetchone()
        state = json.loads(row[0]) if row else {"state": "offline", "message": "Conector USB pendiente."}
        command = db.execute("SELECT value FROM settings WHERE key='sync_request'").fetchone()
        state["request"] = command[0] if command else ""
        return state


def save_inventory(root, payload):
    with database(root) as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES ('inventory',?)",
                   (json.dumps({**payload, "at": now()}, ensure_ascii=False),))


def inventory(root):
    with database(root) as db:
        row = db.execute("SELECT value FROM settings WHERE key='inventory'").fetchone()
    return json.loads(row[0]) if row else None


def on_kobo(record, books, seen):
    """Where a delivered edition really is, judged from the last inventory of the reader."""
    if seen is None or record["delivery"] != "sent":
        return None
    if record["id"] in books:
        return "imported"
    if record["delivered_at"] and record["delivered_at"] > seen["at"]:
        return "copied"
    return "not_imported" if record["id"] in seen.get("unimported", []) else "missing"


def request_sync(root):
    with database(root) as db:
        value = str(uuid.uuid4())
        db.execute("INSERT OR REPLACE INTO settings VALUES ('sync_request',?)", (value,))
        return {"request": value}


def dashboard(root):
    catalogue = records(root)
    with database(root) as db:
        events = [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 30")]
    seen = inventory(root)
    books = {b["edition"]: b for b in (seen or {}).get("books", []) if b.get("edition")}
    return {"publications": [{**{k: r.get(k) for k in
            ("id", "title", "subtitle", "created_at", "style", "writing_mode", "study_aids", "filename", "available", "bytes", "pinned", "delivery", "delivered_at", "archived_at")},
            "on_kobo": on_kobo(r, books, seen), "percent_read": books.get(r["id"], {}).get("percent")}
            for r in catalogue], "storage": storage(root), "device": device_state(root),
            "kobo": {"at": seen["at"], "books": seen["books"]} if seen else None,
            "events": [{**r, "data": json.loads(r["data"])} for r in events]}


def save_annotations(root, highlights):
    with database(root) as db:
        for value in highlights:
            key = hashlib.sha256((value["volume_id"] + "\0" + value["id"]).encode()).hexdigest()
            db.execute("INSERT OR REPLACE INTO annotations VALUES (?,?,?)",
                       (key, json.dumps(value, ensure_ascii=False), now()))


def backup(root):
    """Consistent logical catalogue plus pinned binaries; excludes generated cache."""
    import tempfile
    import os
    import zipfile
    with LOCK:
        catalogue = records(root)
        required = (Path(root) / ".library.sqlite").stat().st_size * 2 + 128_000_000
        for record in catalogue:
            required += (Path(root) / record["id"] / "manifest.json").stat().st_size
            if record["pinned"] or record["delivery"] in {"queued", "transferring"}:
                required += record["bytes"]
        if shutil.disk_usage(tempfile.gettempdir()).free < required:
            raise ValueError("Falta espacio temporal para exportar la biblioteca protegida.")
        fd, name = tempfile.mkstemp(prefix="margen-backup-", suffix=".zip")
        os.close(fd)
        path = Path(name)
        try:
            with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
                with database(root) as db, archive.open("catalogue.sql", "w", force_zip64=True) as output:
                    for line in db.iterdump():
                        output.write((line + "\n").encode())
                for record in catalogue:
                    folder = Path(root) / record["id"]
                    archive.write(folder / "manifest.json", record["id"] + "/manifest.json")
                    if record["pinned"] or record["delivery"] in {"queued", "transferring"}:
                        for name in (record["filename"], "cover.svg"):
                            if (folder / name).is_file():
                                archive.write(folder / name, record["id"] + "/" + name)
            return path
        except BaseException:
            path.unlink(missing_ok=True)
            raise


def drafts(root, identity=None, payload=None):
    with database(root) as db:
        if identity:
            edition(identity)
            if payload is None:
                db.execute("DELETE FROM drafts WHERE id=?", (identity,))
            else:
                db.execute("INSERT OR REPLACE INTO drafts VALUES (?,?,?)",
                           (identity, json.dumps(payload, ensure_ascii=False), now()))
        return [{"id": r["id"], **json.loads(r["value"]), "updated_at": r["updated_at"]}
                for r in db.execute("SELECT * FROM drafts ORDER BY updated_at DESC")]
