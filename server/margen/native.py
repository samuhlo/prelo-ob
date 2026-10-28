"""macOS USB worker. Reads Kobo snapshots; appends notes through the local LiveSync vault."""
import fcntl
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unicodedata
import urllib.request
import urllib.error
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import yaml
from . import __version__


def digest(value):
    return hashlib.sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    temp = path.with_suffix(".partial")
    with temp.open("w") as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def properties(text):
    match = re.match(r"\A\ufeff?---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if not match:
        return {}
    value = yaml.safe_load(match.group(1))
    return value if isinstance(value, dict) else {}


def frontmatter_prefix(path):
    # Read through the closing delimiter, never scan examples in the body.
    with path.open() as stream:
        first = stream.readline()
        if first.lstrip("\ufeff").rstrip("\r\n") != "---":
            return ""
        lines = [first]
        for line in stream:
            lines.append(line)
            if line.rstrip("\r\n") == "---":
                return "".join(lines)
    return ""


def relative(root, value):
    parts = value.replace("\\", "/").split("/")
    if value.startswith("/") or any(p in {"", ".", ".."} for p in parts):
        raise ValueError("Ruta fuera del vault.")
    target = root.joinpath(*parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("El enlace simbólico sale del vault.")
    return target


@contextmanager
def kobo_snapshot(mount):
    """Read-only copy of the reader database; the original is never opened by sqlite."""
    database = mount / ".kobo/KoboReader.sqlite"
    wal = database.with_name(database.name + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise ValueError("El Kobo tiene cambios pendientes. Expulsa y vuelve a conectar el lector.")
    before = database.stat()
    with tempfile.TemporaryDirectory(prefix="margen-kobo-") as folder:
        snapshot = Path(folder) / "reader.sqlite"
        shutil.copyfile(database, snapshot)
        after = database.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or (wal.exists() and wal.stat().st_size):
            raise ValueError("La base del lector cambió durante la lectura. Se reintentará.")
        db = sqlite3.connect("file:" + quote(str(snapshot)) + "?mode=ro&immutable=1", uri=True)
        db.row_factory = sqlite3.Row
        try:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("La copia de la base del Kobo no supera la comprobación de integridad.")
            yield db
        finally:
            db.close()


def read_kobo(mount):
    with kobo_snapshot(mount) as db:
        columns = {r["name"] for r in db.execute("PRAGMA table_info(Bookmark)")}
        if not {"BookmarkID", "VolumeID"}.issubset(columns):
            raise ValueError("No se reconoce la tabla de subrayados del Kobo.")
        book_columns = {r["name"] for r in db.execute("PRAGMA table_info(content)")}
        books = {}
        if "ContentID" in book_columns:
            selected = [name for name in ["ContentID", "Title", "Attribution"] if name in book_columns]
            sql = "SELECT " + ", ".join('"' + name + '"' for name in selected) + " FROM content" + (" WHERE ContentType=6" if "ContentType" in book_columns else "")
            books = {str(r["ContentID"]): dict(r) for r in db.execute(sql)}
        result = []
        string = lambda value: "" if value is None else str(value)
        # Firmware stores opaque bytes in fields such as ExtraAnnotationData,
        # sometimes declared as TEXT. Do not ask sqlite3 to decode unused fields.
        selected = [name for name in ["BookmarkID", "VolumeID", "ContentID", "StartContainerPath",
                    "Text", "Annotation", "DateCreated", "Hidden", "Color", "Colour"] if name in columns]
        sql = "SELECT " + ", ".join('"' + name + '"' for name in selected) + " FROM Bookmark"
        for row in db.execute(sql):
            row = dict(row)
            if str(row.get("Hidden", "")).lower() in {"true", "1"} or not (row.get("Text") or row.get("Annotation")):
                continue
            book = books.get(string(row.get("VolumeID")), {})
            result.append({
                "id": string(row.get("BookmarkID")), "volume_id": string(row.get("VolumeID")),
                "content_id": string(row.get("ContentID")), "start_path": string(row.get("StartContainerPath")),
                "text": string(row.get("Text")), "annotation": string(row.get("Annotation")),
                "title": string(book.get("Title")), "author": string(book.get("Attribution")),
                "created_at": string(row.get("DateCreated")), "color": string(row.get("Color", row.get("Colour"))),
            })
        return result


ONBOARD = "file:///mnt/onboard/"
EDITION_FILE = re.compile(r"margen-([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.epub")



def book_checksum(mount, path):
    target = relative(mount, path)
    if target.is_symlink() or not target.is_file():
        return ""
    with target.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_books(mount):
    """Books the reader has imported, plus Prelo files still waiting to be imported."""
    with kobo_snapshot(mount) as db:
        columns = {r["name"] for r in db.execute("PRAGMA table_info(content)")}
        if "ContentID" not in columns:
            return {"books": [], "unimported": []}
        wanted = [c for c in ["ContentID", "Title", "Attribution", "___PercentRead", "DateLastRead", "ReadStatus"] if c in columns]
        sql = "SELECT " + ", ".join('"' + c + '"' for c in wanted) + " FROM content" + (" WHERE ContentType=6" if "ContentType" in columns else "")
        rows = [dict(r) for r in db.execute(sql)]
    string = lambda value: "" if value is None else str(value)
    books, imported = [], set()
    for row in rows:
        content = string(row.get("ContentID"))
        path = content.removeprefix(ONBOARD) if content.startswith(ONBOARD) else ""
        match = EDITION_FILE.fullmatch(path)
        if match:
            imported.add(match[1])
        try:
            percent = max(0, min(100, int(float(row.get("___PercentRead") or 0))))
        except ValueError:
            percent = 0
        books.append({"id": content[:500], "path": path[:500], "edition": match[1] if match else "",
                      "title": string(row.get("Title"))[:300], "author": string(row.get("Attribution"))[:300],
                      "percent": percent, "last_read": string(row.get("DateLastRead"))[:40],
                      "status": string(row.get("ReadStatus"))[:10],
                      "present": bool(path) and ".." not in path.split("/") and (mount / path).is_file(),
                      "sha256": book_checksum(mount, path) if path and ".." not in path.split("/") else ""})
    waiting = sorted(m[1] for f in mount.glob("margen-*.epub") if (m := EDITION_FILE.fullmatch(f.name)) and m[1] not in imported)
    return {"books": books, "unimported": waiting}


def caption_date(value):
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})(?:T| |$)", value.strip())
    if not match:
        return value
    try:
        year, month, day = map(int, match.groups())
        return datetime(year, month, day).strftime("%d/%m/%Y")
    except ValueError:
        return value


def highlight_block(highlight, source):
    fingerprint = digest(json.dumps([highlight["text"], highlight["annotation"]], ensure_ascii=False, separators=(",", ":")))[:20]
    marker = f'<!-- margen:{highlight["key"]}:{fingerprint} -->'
    lines = [marker, "", *["> " + line for line in highlight["text"].split("\n")], ""]
    if highlight["annotation"]:
        lines += ["**Anotación en Kobo:**", "", *["> " + line for line in highlight["annotation"].split("\n")], ""]
    if source:
        lines += [f"Origen: [[{source.removesuffix('.md')}]]", ""]
    elif highlight["match"] == "unresolved" or highlight.get("source"):
        lines += ["*Origen pendiente de vincular.*", ""]
    if highlight.get("content_note"):
        lines += [highlight["content_note"], ""]
    if highlight.get("publication_id"):
        lines += [f'Edición: {highlight["publication_title"]} · {highlight["publication_id"]}', ""]
    if highlight["created_at"]:
        lines += ["Fecha : " + caption_date(highlight["created_at"]), ""]
    return marker, "\n".join(lines) + "\n---\n"


def append_notes(vault, folder, highlights):
    directory = relative(vault, folder)
    directory.mkdir(parents=True, exist_ok=True)
    by_group, source_paths, key_groups = {}, {}, {}
    issues, blocked_keys, blocked_groups = [], set(), set()
    for path in directory.glob("*.md"):
        if "sync-conflict" in path.name or path.is_symlink():
            continue
        text = path.read_text()
        try:
            identity = properties(text).get("margen_lectura")
            if identity is not None and not isinstance(identity, str):
                raise ValueError()
        except (yaml.YAMLError, ValueError):
            issues.append({"kind": "invalid_frontmatter", "path": path.relative_to(vault).as_posix()})
            blocked_keys.update(re.findall(r"<!-- margen:([a-f0-9]{64}):", text))
            # An invalid note can still declare a recognizable group in its YAML prefix.
            # Use it only to defer that group, never to assign provenance or rewrite the note.
            header = re.match(r"\A\ufeff?---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
            if header:
                for line in header[1].splitlines():
                    if not line.startswith("margen_lectura:"):
                        continue
                    try:
                        group = yaml.safe_load(line).get("margen_lectura")
                        if isinstance(group, str):
                            blocked_groups.add(group)
                    except (yaml.YAMLError, ValueError):
                        pass
            continue
        if identity:
            if identity in by_group:
                blocked_groups.add(identity)
                issues.append({"kind": "duplicate_identity", "path": path.relative_to(vault).as_posix()})
            by_group[identity] = path
            for key in re.findall(r"<!-- margen:([a-f0-9]{64}):", text):
                if key in key_groups and key_groups[key] != identity:
                    blocked_keys.add(key)
                key_groups[key] = identity
    needed = {h["source"]["id"] for h in highlights if h.get("source")}
    duplicates = set()
    for path in vault.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(vault).parts) or path.is_symlink():
            continue
        # Only read the YAML prefix when locating identities.
        prefix = frontmatter_prefix(path)
        try:
            identity = properties(prefix).get("margen_id")
        except (yaml.YAMLError, ValueError):
            continue
        if isinstance(identity, str) and identity in needed:
            if identity in source_paths:
                duplicates.add(identity)
            source_paths[identity] = path.relative_to(vault).as_posix()
    for identity in duplicates:
        source_paths.pop(identity, None)
    groups = {}
    for h in highlights:
        if h["key"] in blocked_keys:
            continue
        requested_group = h["source"]["id"] if h.get("source") else digest(h["volume_id"])[:20]
        if requested_group in blocked_groups:
            continue
        group = key_groups.get(h["key"]) or requested_group
        if group not in blocked_groups:
            groups.setdefault(group, []).append(h)
    added, unresolved = 0, 0
    for group, items in groups.items():
        first = items[0]
        title = (first.get("source") or {}).get("title") or first.get("publication_title") or first["title"] or "Lectura"
        source = None
        source_id = first["source"]["id"] if first.get("source") else None
        if source_id and source_id not in duplicates:
            source = source_paths.get(source_id)
            candidate = relative(vault, first["source"]["path"])
            if not source and candidate.is_file():
                try:
                    identity = properties(candidate.read_text()).get("margen_id")
                except (yaml.YAMLError, ValueError):
                    identity = "invalid"
                if identity is None or identity == source_id:
                    source = first["source"]["path"]
        unresolved += sum(bool(h.get("source") and not source or h["match"] == "unresolved") for h in items)
        target = by_group.get(group)
        if target is None:
            slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()).strip("-")[:140].rstrip("-") or "lectura"
            stem = "subrayados-" + slug
            for suffix in range(1, 10000):
                target = directory / (stem + (f"-{suffix}" if suffix > 1 else "") + ".md")
                if not target.exists():
                    break
            else:
                raise ValueError("Demasiadas notas con el mismo título.")
            fields = {"tipo": "fuente_externa", "zona": "cerebro", "area": "media_consumo",
                      "formato": "subrayados", "tags": [], "relacionadas": [], "margen_lectura": group}
            if source:
                fields["fuente_nota"] = "[[" + source.removesuffix(".md") + "]]"
            if first["author"]:
                fields["fuente_autor"] = first["author"]
            original = ""
            current = "---\n" + yaml.safe_dump(fields, allow_unicode=True, sort_keys=False) + "---\n\n# Subrayados — " + title.replace("\n", " ") + "\n"
        else:
            original = target.read_text()
            current = original
        count = 0
        for h in items:
            marker, block = highlight_block(h, source)
            if marker in current:
                continue
            update = f'<!-- margen:{h["key"]}:' in current
            current = current.rstrip() + "\n\n" + ("**Actualización del subrayado**\n\n" if update else "") + block
            count += 1
        if not count:
            continue
        if original:
            # Append only. A concurrent editor/LiveSync replacement is detected before writing.
            with target.open("r+") as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
                if stream.read() != original or os.fstat(stream.fileno()).st_ino != target.stat().st_ino:
                    raise ValueError("Una nota cambió durante la importación. Se reintentará sin sustituirla.")
                stream.seek(0, os.SEEK_END)
                stream.write(current[len(original):] if current.startswith(original) else "\n\n" + current[len(original.rstrip()):].lstrip("\n"))
                stream.flush()
                os.fsync(stream.fileno())
        else:
            with target.open("x") as stream:
                stream.write(current)
                stream.flush()
                os.fsync(stream.fileno())
        added += count
    return {"examined": len(highlights), "added": added, "unresolved": unresolved,
            "skipped": len(highlights) - sum(map(len, groups.values())), "issues": issues}


class Worker:
    def __init__(self, config):
        self.config = config
        self.vault = Path(config["vault"])
        self.state = Path(config["state"])
        self.state.mkdir(parents=True, exist_ok=True)
        self.last_sync = None
        if (self.state / "last-sync.json").is_file():
            self.last_sync = json.loads((self.state / "last-sync.json").read_text())

    def api(self, route, body=None, binary=False):
        request = urllib.request.Request(self.config["server_url"].rstrip("/") + route,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + self.config["token"], "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        return data if binary else json.loads(data)

    def report(self, state, message, device=""):
        return self.api("/v1/device", {"state": state, "message": message, "device": device, "last_sync": self.last_sync, "version": __version__})

    def synchronize(self, mount):
        with (self.state / "usb.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            version = mount / ".kobo/version"
            device = digest(version.read_bytes() if version.is_file() else str(mount))[:20]
            self.report("working", "Recogiendo subrayados del Kobo.", device)
            # Taken before copying: it shows what the reader imported after the previous connection.
            self.api("/v1/device/inventory", {"device": device, **read_books(mount)})
            raw = read_kobo(mount)
            resolved = []
            for offset in range(0, len(raw), 100):
                resolved += self.api("/v1/annotations", {"highlights": raw[offset:offset + 100]})["highlights"]
            result = append_notes(self.vault, self.config["highlights_folder"], resolved)
            changes = self.carry_out(mount, device)
            sent = 0
            for publication in self.api("/v1/deliveries"):
                identity = publication["id"]
                if not re.fullmatch(r"[a-f0-9-]{36}", identity) or publication["filename"] != f"margen-{identity}.epub":
                    raise ValueError("Nombre de publicación no válido.")
                self.api(f"/v1/deliveries/{identity}/claim", {"device": device})
                self.report("working", "Copiando publicaciones pendientes.", device)
                data = self.api(f"/v1/publications/{identity}/epub", binary=True)
                checksum = digest(data)
                target = mount / publication["filename"]
                partial = mount / (".margen-" + identity + ".partial")
                if target.exists():
                    if digest(target.read_bytes()) != checksum:
                        raise ValueError("Ya existe en el Kobo una edición con contenido distinto. Se conserva para revisarla.")
                else:
                    partial.unlink(missing_ok=True)
                    with partial.open("xb") as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    if digest(partial.read_bytes()) != checksum:
                        raise ValueError("La copia USB no coincide; queda pendiente.")
                    if target.exists():
                        raise ValueError("La edición apareció durante la copia. Se reintentará.")
                    partial.rename(target)
                if digest(target.read_bytes()) != checksum:
                    raise ValueError("La verificación final de la copia USB falló.")
                self.api(f"/v1/deliveries/{identity}/receipt", {"checksum": checksum, "device": device})
                sent += 1
            self.last_sync = {"at": stamp(), **result, "sent": sent, "changes": changes, "device": device}
            atomic_json(self.state / "last-sync.json", self.last_sync)
            summary = [f'{result["added"]} subrayados nuevos o actualizados']
            if sent:
                summary.append(f"{sent} revistas copiadas")
            if changes:
                summary.append(f"{changes} cambios aplicados")
            if result["issues"]:
                summary.append(f"{len(result['issues'])} notas necesitan revisar sus propiedades; se conservan las citas en el servicio")
            self.report("error" if result["issues"] else "ready", " · ".join(summary) + (". Los cambios aparecerán al desconectar el Kobo." if sent or changes else "."), device)
            if self.config.get("auto_eject", True):
                subprocess.run(["/usr/sbin/diskutil", "eject", str(mount)], check=True, capture_output=True, timeout=25)
            return self.last_sync

    def carry_out(self, mount, device):
        """Removals and uploads requested from any computer since the last connection."""
        done = 0
        for command in self.api("/v1/kobo/commands?device=" + quote(device)):
            identity = command["id"]
            if not re.fullmatch(r"[a-f0-9-]{36}", identity):
                raise ValueError("Orden no válida.")
            # Claim before touching the reader. Cancellation is only promised while still pending.
            try:
                command = self.api(f"/v1/kobo/commands/{identity}/claim", {"device": device})
            except urllib.error.HTTPError as error:
                if error.code == 409:
                    continue
                raise
            receipt = {"device": device, "claim_token": command["claim_token"]}
            try:
                parts = command["path"].split("/")
                if any(p in {"", ".", ".."} or p.startswith(".") for p in parts) or not command["path"].lower().endswith(".epub"):
                    raise ValueError("Ruta de libro no válida en el Kobo.")
                target = relative(mount, command["path"])
                if target.is_symlink():
                    raise ValueError("El archivo no puede ser un enlace simbólico.")
                self.report("working", "Aplicando los cambios pedidos desde Prelo.", device)
                if command["kind"] == "remove":
                    if target.exists() and book_checksum(mount, command["path"]) != command["sha256"]:
                        raise ValueError("El libro cambió desde la solicitud. Se conserva; vuelve a revisar el inventario.")
                    target.unlink(missing_ok=True)
                elif command["kind"] == "upload":
                    data = self.api(f"/v1/kobo/uploads/{identity}", binary=True)
                    if digest(data) != command["sha256"]:
                        raise ValueError("La subida no coincide con el archivo enviado.")
                    if target.exists():
                        if digest(target.read_bytes()) != command["sha256"]:
                            raise ValueError("Ya hay en el Kobo otro libro con ese nombre. Cámbiale el nombre y vuelve a enviarlo.")
                    else:
                        partial = mount / (".margen-" + identity + ".partial")
                        with partial.open("wb") as stream:
                            stream.write(data)
                            stream.flush()
                            os.fsync(stream.fileno())
                        if digest(partial.read_bytes()) != command["sha256"]:
                            partial.unlink(missing_ok=True)
                            raise ValueError("La copia USB no coincide; queda pendiente.")
                        target.parent.mkdir(parents=True, exist_ok=True)
                        partial.rename(target)
                else:
                    raise ValueError("Orden desconocida.")
            except ValueError as error:
                self.api(f"/v1/kobo/commands/{identity}/done", {**receipt, "ok": False, "message": str(error)[:500]})
                continue
            self.api(f"/v1/kobo/commands/{identity}/done", {**receipt, "ok": True, "message": ""})
            done += 1
        return done

    def run(self):
        seen, request_id = None, ""
        while True:
            try:
                mounts = [p for p in Path(self.config.get("volumes", "/Volumes")).iterdir()
                          if p.is_dir() and (p / ".kobo/KoboReader.sqlite").is_file()]
                if not mounts:
                    seen = None
                    state = self.report("disconnected", "Conecta el Kobo al Mac y acepta «Conectar» en su pantalla.")
                    request_id = state["request"]
                else:
                    mount = mounts[0]
                    state = self.api("/v1/device")
                    pending = self.api("/v1/deliveries") or self.api("/v1/kobo/commands?device=" + quote(digest((mount / ".kobo/version").read_bytes() if (mount / ".kobo/version").is_file() else str(mount))[:20]))
                    if seen != str(mount) or state["request"] != request_id or pending:
                        self.synchronize(mount)
                        seen = str(mount)
                        request_id = state["request"]
                    else:
                        self.report("ready", "Kobo conectado; todo sincronizado.")
                time.sleep(5)
            except Exception as error:
                # Never log note text, credentials, request bodies or arbitrary server responses.
                message = str(error) if isinstance(error, ValueError) else "No se pudo completar la sincronización. Se reintentará al recuperar la conexión."
                try:
                    self.report("error", message[:500])
                except Exception:
                    pass
                print(stamp(), type(error).__name__, flush=True)
                time.sleep(20)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    Worker(config).run()


if __name__ == "__main__":
    main()
