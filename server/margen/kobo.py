"""Reader management from any computer: orders the Mac's USB connector carries out on the next connection."""
import hashlib
import io
import json
import re
import uuid
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from .library import LOCK, database, inventory, now, records, storage

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
    size = data.stat().st_size if isinstance(data, Path) else len(data)
    if size > MAX_UPLOAD:
        raise ValueError("El EPUB supera los 200 MB.")
    try:
        with zipfile.ZipFile(data if isinstance(data, Path) else io.BytesIO(data)) as book:
            first = book.infolist()[0]
            if first.filename != "mimetype" or first.file_size != 20 or first.compress_type != zipfile.ZIP_STORED or book.read(first) != b"application/epub+zip":
                raise ValueError
            book.getinfo("META-INF/container.xml")
    except (zipfile.BadZipFile, ValueError, KeyError, IndexError):
        raise ValueError("El archivo no es un EPUB válido.") from None


def row(record):
    return {k: record[k] for k in ("id", "kind", "path", "title", "state", "message", "created_at", "done_at")}


def listing(root):
    with database(root) as db:
        return [row(r) for r in db.execute("SELECT * FROM kobo_commands ORDER BY created_at DESC LIMIT 100")]


def pending(root, device=""):
    # Old connectors do not identify the reader and must never receive destructive orders.
    if not device:
        return []
    with database(root) as db:
        return [{**row(r), "sha256": r["sha256"]} for r in db.execute(
            """SELECT c.* FROM kobo_commands c JOIN kobo_command_targets t ON c.id=t.id
               WHERE t.device=? AND c.state IN ('pending','executing') ORDER BY created_at""", (device,))]


def destination(root, device):
    seen = inventory(root) or {}
    if not device or seen.get("device") != device:
        raise ValueError("Conecta el Kobo y actualiza su inventario antes de pedir este cambio.")
    return seen


def claim(root, identity, device):
    identity = str(uuid.UUID(identity))
    with database(root) as db:
        db.execute("BEGIN IMMEDIATE")
        found = db.execute("""SELECT c.*,t.device,t.claim_token FROM kobo_commands c
            JOIN kobo_command_targets t ON c.id=t.id WHERE c.id=?""", (identity,)).fetchone()
        if not found or found["device"] != device or found["state"] not in {"pending", "executing"}:
            raise ValueError("La orden no está disponible para este lector.")
        token = found["claim_token"] or str(uuid.uuid4())
        db.execute("UPDATE kobo_command_targets SET claim_token=? WHERE id=?", (token, identity))
        db.execute("UPDATE kobo_commands SET state='executing' WHERE id=?", (identity,))
        return {**row(found), "state": "executing", "sha256": found["sha256"], "claim_token": token}


def request_removal(root, path, device=""):
    path = book_path(path)
    seen = destination(root, device)
    books = {b["path"]: b for b in seen.get("books", []) if b.get("path")}
    delivered = {r["filename"]: r for r in records(root) if r["delivery"] == "sent"}
    if path not in books and path not in delivered:
        raise ValueError("Ese libro no figura en el último inventario del Kobo.")
    checksum = books[path].get("sha256") if path in books else delivered[path].get("checksum")
    if not checksum or path not in books and delivered[path].get("device") != device:
        raise ValueError("Falta verificar el archivo. Vuelve a conectar el Kobo antes de retirarlo.")
    title = books[path]["title"] if path in books else delivered[path]["title"]
    with database(root) as db:
        existing = db.execute("SELECT * FROM kobo_commands WHERE state IN ('pending','executing') AND path=?", (path,)).fetchone()
        if existing:
            if existing["kind"] == "remove":
                return row(existing)
            raise ValueError("Ese libro tiene una subida pendiente. Cancélala en su lugar.")
        identity = str(uuid.uuid4())
        db.execute("INSERT INTO kobo_commands VALUES (?,?,?,?,?,?,?,?,?)",
                   (identity, "remove", path, title or path, checksum, "pending", None, now(), None))
        db.execute("INSERT INTO kobo_command_targets(id,device) VALUES (?,?)", (identity, device))
        return row(db.execute("SELECT * FROM kobo_commands WHERE id=?", (identity,)).fetchone())


def upload(root, filename, data, device=""):
    destination(root, device)
    check_epub(data)
    name = upload_name(filename)
    identity = str(uuid.uuid4())
    folder = Path(root) / ".uploads"
    folder.mkdir(exist_ok=True)
    target = folder / (identity + ".epub")
    size = data.stat().st_size if isinstance(data, Path) else len(data)
    with LOCK:
        state = storage(root)
        if state["used_bytes"] + size > state["limit_bytes"]:
            raise ValueError("La subida no cabe en la cuota. Libera espacio o amplía el límite.")
        if state["free_disk_bytes"] < size + 128_000_000:
            raise ValueError("Falta espacio para guardar la subida.")
        try:
            with database(root) as db:
                if db.execute("SELECT 1 FROM kobo_commands WHERE state IN ('pending','executing') AND path=?", (name,)).fetchone():
                    raise ValueError("Ya hay un EPUB con ese nombre pendiente de enviar.")
                if isinstance(data, Path):
                    data.replace(target)
                else:
                    target.write_bytes(data)
                with target.open("rb") as stream:
                    checksum = hashlib.file_digest(stream, "sha256").hexdigest()
                db.execute("INSERT INTO kobo_commands VALUES (?,?,?,?,?,?,?,?,?)",
                           (identity, "upload", name, name.removesuffix(".epub"), checksum,
                            "pending", None, now(), None))
                db.execute("INSERT INTO kobo_command_targets(id,device) VALUES (?,?)", (identity, device))
                result = row(db.execute("SELECT * FROM kobo_commands WHERE id=?", (identity,)).fetchone())
            return result
        except BaseException:
            target.unlink(missing_ok=True)
            raise


def upload_file(root, identity):
    path = Path(root) / ".uploads" / (str(uuid.UUID(identity)) + ".epub")
    if not path.is_file():
        raise FileNotFoundError(identity)
    return path


def cancel(root, identity):
    identity = str(uuid.UUID(identity))
    with database(root) as db:
        if not db.execute("UPDATE kobo_commands SET state='cancelled',done_at=? WHERE id=? AND state IN ('pending','failed')",
                          (now(), identity)).rowcount:
            raise ValueError("La orden ya se está ejecutando o ha terminado; no se ha cancelado.")
    (Path(root) / ".uploads" / (identity + ".epub")).unlink(missing_ok=True)


def complete(root, identity, ok, message="", device="", claim_token=""):
    identity = str(uuid.UUID(identity))
    with database(root) as db:
        db.execute("BEGIN IMMEDIATE")
        found = db.execute("""SELECT c.state,t.device,t.claim_token FROM kobo_commands c
            JOIN kobo_command_targets t ON c.id=t.id WHERE c.id=?""", (identity,)).fetchone()
        if not found or not claim_token or found["device"] != device or found["claim_token"] != claim_token:
            raise ValueError("No se puede confirmar una orden sin reclamarla para este lector.")
        state = "done" if ok else "failed"
        if found["state"] != state:
            if found["state"] != "executing":
                raise ValueError("Esa orden ya no está en ejecución.")
            db.execute("UPDATE kobo_commands SET state=?,message=?,done_at=? WHERE id=?",
                       (state, message[:500], now(), identity))
    if ok:
        (Path(root) / ".uploads" / (identity + ".epub")).unlink(missing_ok=True)


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
    return {"device": (seen or {}).get("device", ""), "at": seen["at"] if seen else None, "books": books, "commands": listing(root)}
