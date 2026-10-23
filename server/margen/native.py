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
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import yaml


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


def relative(root, value):
    parts = value.replace("\\", "/").split("/")
    if value.startswith("/") or any(p in {"", ".", ".."} for p in parts):
        raise ValueError("Ruta fuera del vault.")
    target = root.joinpath(*parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("El enlace simbólico sale del vault.")
    return target


def read_kobo(mount):
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
        finally:
            db.close()


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
    by_group, source_paths = {}, {}
    for path in directory.glob("*.md"):
        if "sync-conflict" in path.name or path.is_symlink():
            continue
        identity = properties(path.read_text()).get("margen_lectura")
        if identity:
            if identity in by_group:
                raise ValueError("Hay dos notas con el mismo margen_lectura. Conserva ambas y revisa el conflicto.")
            by_group[identity] = path
    needed = {h["source"]["id"] for h in highlights if h.get("source")}
    duplicates = set()
    for path in vault.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(vault).parts) or path.is_symlink():
            continue
        # Only read the YAML prefix when locating identities.
        with path.open() as stream:
            prefix = stream.read(16_384)
        match = re.search(r'^margen_id:\s*["\']?([a-zA-Z0-9_-]+)', prefix, re.M)
        if match and match[1] in needed:
            identity = match[1]
            if identity in source_paths:
                duplicates.add(identity)
            source_paths[identity] = path.relative_to(vault).as_posix()
    for identity in duplicates:
        source_paths.pop(identity, None)
    groups = {}
    for h in highlights:
        group = h["source"]["id"] if h.get("source") else digest(h["volume_id"])[:20]
        groups.setdefault(group, []).append(h)
    added, unresolved = 0, 0
    for group, items in groups.items():
        first = items[0]
        title = (first.get("source") or {}).get("title") or first.get("publication_title") or first["title"] or "Lectura"
        source = None
        if first.get("source") and group not in duplicates:
            source = source_paths.get(group)
            candidate = relative(vault, first["source"]["path"])
            if not source and candidate.is_file():
                identity = properties(candidate.read_text()).get("margen_id")
                if identity in {None, group}:
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
    return {"examined": len(highlights), "added": added, "unresolved": unresolved}


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
        return self.api("/v1/device", {"state": state, "message": message, "device": device, "last_sync": self.last_sync})

    def synchronize(self, mount):
        with (self.state / "usb.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            version = mount / ".kobo/version"
            device = digest(version.read_bytes() if version.is_file() else str(mount))[:20]
            self.report("working", "Recogiendo subrayados del Kobo.", device)
            raw = read_kobo(mount)
            resolved = []
            for offset in range(0, len(raw), 100):
                resolved += self.api("/v1/annotations", {"highlights": raw[offset:offset + 100]})["highlights"]
            result = append_notes(self.vault, self.config["highlights_folder"], resolved)
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
            self.last_sync = {"at": stamp(), **result, "sent": sent, "device": device}
            atomic_json(self.state / "last-sync.json", self.last_sync)
            self.report("ready", f'{result["added"]} subrayados nuevos o actualizados · {sent} revistas enviadas.', device)
            if self.config.get("auto_eject", True):
                subprocess.run(["/usr/sbin/diskutil", "eject", str(mount)], check=True, capture_output=True, timeout=25)
            return self.last_sync

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
                    pending = self.api("/v1/deliveries")
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
