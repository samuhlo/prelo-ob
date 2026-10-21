"""Restore a trusted Prelo export into a NEW directory for inspection or recovery."""
import argparse
import json
import re
import sqlite3
import zipfile
from pathlib import Path


def restore(archive_path, destination):
    destination = Path(destination)
    if destination.exists():
        raise ValueError("El destino ya existe. Usa una carpeta nueva para conservar los datos actuales.")
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if "catalogue.sql" not in names:
            raise ValueError("Falta el catálogo.")
        allowed = re.compile(r"^[0-9a-f-]{36}/(?:manifest\.json|cover\.svg|margen-[0-9a-f-]{36}\.epub)$")
        if any(name != "catalogue.sql" and not allowed.fullmatch(name) for name in names):
            raise ValueError("El archivo contiene rutas no reconocidas.")
        if archive.testzip():
            raise ValueError("El archivo no supera la comprobación de integridad.")
        destination.mkdir(parents=True)
        for name in names:
            if name == "catalogue.sql":
                continue
            target = destination / name
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(archive.read(name))
        with sqlite3.connect(destination / ".library.sqlite") as db:
            # Exports contain only schema and literal INSERTs. Reject access outside this DB.
            denied = {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH, sqlite3.SQLITE_FUNCTION,
                      sqlite3.SQLITE_PRAGMA, sqlite3.SQLITE_CREATE_TRIGGER, sqlite3.SQLITE_CREATE_VIEW}
            db.set_authorizer(lambda operation, *args: sqlite3.SQLITE_DENY if operation in denied else sqlite3.SQLITE_OK)
            db.executescript(archive.read("catalogue.sql").decode())
            db.set_authorizer(None)
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("El catálogo restaurado no es íntegro.")
            editions = db.execute("SELECT count(*) FROM editions").fetchone()[0]
            annotations = db.execute("SELECT count(*) FROM annotations").fetchone()[0]
    return {"editions": editions, "annotations": annotations, "restored_to": str(destination)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(json.dumps(restore(args.archive, args.destination), ensure_ascii=False))
