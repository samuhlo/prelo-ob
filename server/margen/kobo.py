"""Reader management from any computer: orders the Mac's USB connector carries out on the next connection."""
import hashlib
import io
import json
import re
import uuid
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from .library import database, inventory, now, records

MAX_UPLOAD = 200_000_000
RESERVED = re.compile(r"^margen-", re.I)


def book_path(value: str) -> str:
    """A sideloaded book on the reader's main storage: relative, visible and an EPUB."""
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or "\\" in value or "\0" in value or len(value) > 400
            or any(part in {"", ".", ".."} or part.startswith(".") for part in path.parts)
            or not value.lower().endswith(".epub")):
        raise ValueError("Ruta de libro no válida en el Kobo.")
    return str(path)


def upload_name(filename: str) -> str:
    stem = Path(filename.replace("\\", "/")).name
    stem = re.sub(r"\.epub$", "", stem, flags=re.I)
    stem = re.sub(r"[^\w .,()'-]+", "_", stem).strip(" ._")[:120] or "libro"
    name = stem + ".epub"
    if RESERVED.match(name):
        raise ValueError("Ese nombre está reservado para las revistas de Prelo.")
    return name


def check_epub(data: bytes):
    if len(data) > MAX_UPLOAD:
        raise ValueError("El EPUB supera los 200 MB.")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as book:
            first = book.infolist()[0]
            if first.filename != "mimetype" or book.read(first).strip() != b"application/epub+zip":
                raise ValueError
            book.getinfo("META-INF/container.xml")
    except (zipfile.BadZipFile, ValueError, KeyError, IndexError):
        raise ValueError("El archivo no es un EPUB válido.") from None


def row(record):
    return {k: record[k] for k in ("id", "kind", "path", "title", "state", "message", "created_at", "done_at")}


def listing(root):
    with database(root) as db:
        return [row(r) for r in db.execute("SELECT * FROM kobo_commands ORDER BY created_at DESC LIMIT 100")]


def pending(root):
    with database(root) as db:
        return [{**row(r), "sha256": r["sha256"]} for r in
                db.execute("SELECT * FROM kobo_commands WHERE state='pending' ORDER BY created_at")]


def request_removal(root, path):
    path = book_path(path)
    seen = inventory(root) or {}
    books = {b["path"]: b for b in seen.get("books", []) if b.get("path")}
    delivered = {r["filename"]: r for r in records(root) if r["delivery"] == "sent"}
    if path not in books and path not in delivered:
        raise ValueError("Ese libro no figura en el último inventario del Kobo.")
    title = books[path]["title"] if path in books else delivered[path]["title"]
    with database(root) as db:
        existing = db.execute("SELECT * FROM kobo_commands WHERE state='pending' AND path=?", (path,)).fetchone()
        if existing:
            if existing["kind"] == "remove":
                return row(existing)
            raise ValueError("Ese libro tiene una subida pendiente. Cancélala en su lugar.")
        identity = str(uuid.uuid4())
        db.execute("INSERT INTO kobo_commands VALUES (?,?,?,?,?,?,?,?,?)",
                   (identity, "remove", path, title or path, None, "pending", None, now(), None))
        return row(db.execute("SELECT * FROM kobo_commands WHERE id=?", (identity,)).fetchone())


def upload(root, filename, data):
    check_epub(data)
    name = upload_name(filename)
    identity = str(uuid.uuid4())
    folder = Path(root) / ".uploads"
    folder.mkdir(exist_ok=True)
    (folder / (identity + ".epub")).write_bytes(data)
    with database(root) as db:
        if db.execute("SELECT 1 FROM kobo_commands WHERE state='pending' AND path=?", (name,)).fetchone():
            (folder / (identity + ".epub")).unlink()
            raise ValueError("Ya hay un EPUB con ese nombre pendiente de enviar.")
        db.execute("INSERT INTO kobo_commands VALUES (?,?,?,?,?,?,?,?,?)",
                   (identity, "upload", name, name.removesuffix(".epub"), hashlib.sha256(data).hexdigest(),
                    "pending", None, now(), None))
        return row(db.execute("SELECT * FROM kobo_commands WHERE id=?", (identity,)).fetchone())


def upload_file(root, identity):
    path = Path(root) / ".uploads" / (str(uuid.UUID(identity)) + ".epub")
    if not path.is_file():
        raise FileNotFoundError(identity)
    return path


def cancel(root, identity):
    with database(root) as db:
        if not db.execute("DELETE FROM kobo_commands WHERE id=? AND state='pending'", (identity,)).rowcount:
            raise ValueError("Esa orden ya no está pendiente.")
    (Path(root) / ".uploads" / (str(uuid.UUID(identity)) + ".epub")).unlink(missing_ok=True)


def complete(root, identity, ok, message=""):
    with database(root) as db:
        if not db.execute("UPDATE kobo_commands SET state=?, message=?, done_at=? WHERE id=? AND state='pending'",
                          ("done" if ok else "failed", message[:500], now(), identity)).rowcount:
            raise ValueError("Esa orden ya no está pendiente.")
    if ok:
        (Path(root) / ".uploads" / (str(uuid.UUID(identity)) + ".epub")).unlink(missing_ok=True)


def annotations(root):
    with database(root) as db:
        return [{"key": r["key"], **json.loads(r["value"])} for r in db.execute("SELECT key, value FROM annotations")]


def highlights(root, volume):
    found = [{k: a.get(k, "") for k in ("key", "text", "annotation", "created_at", "color")}
             for a in annotations(root) if a.get("volume_id") == volume]
    return sorted(found, key=lambda h: h["created_at"])


def overview(root):
    seen = inventory(root)
    counts = Counter(a.get("volume_id") for a in annotations(root))
    books = [{**b, "highlights": counts.get(b["id"], 0)} for b in (seen or {}).get("books", [])]
    return {"at": seen["at"] if seen else None, "books": books, "commands": listing(root)}
