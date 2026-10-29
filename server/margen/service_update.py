"""Service updates requested from Obsidian and carried out on the Mac by the USB connector."""
import json
import re
from datetime import datetime, timezone
from . import __version__, library

VERSION = r"^(0|[1-9]\d{0,3})\.(0|[1-9]\d{0,3})\.(0|[1-9]\d{0,3})$"
UNCLAIMED_SECONDS = 10 * 60
SILENT_SECONDS = 40 * 60


def parse(value):
    match = re.fullmatch(VERSION, value or "")
    return tuple(int(part) for part in match.groups()) if match else None


def age(stamp):
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds()
    except (TypeError, ValueError):
        return float("inf")


def view(value):
    """The stored request as the service sees it now: a restarted service proves its own version."""
    if not value or value["state"] not in {"requested", "running"}:
        return value
    if parse(__version__) >= parse(value["version"]):
        return {**value, "state": "complete", "message": f"Servidor actualizado a {__version__}."}
    if value["state"] == "requested" and age(value["requested_at"]) > UNCLAIMED_SECONDS:
        return {**value, "state": "failed",
                "message": "El conector USB del Mac no recogió la petición. Comprueba que el Mac está encendido y vuelve a intentarlo."}
    if value["state"] == "running" and age(value["updated_at"]) > SILENT_SECONDS:
        return {**value, "state": "failed", "message": "La actualización no terminó. Revisa logs/update.log en el Mac."}
    return value


def _load(db):
    row = db.execute("SELECT value FROM settings WHERE key='service_update'").fetchone()
    return json.loads(row[0]) if row else None


def _store(db, value):
    db.execute("INSERT OR REPLACE INTO settings VALUES ('service_update',?)", (json.dumps(value, ensure_ascii=False),))
    return view(value)


def current(root):
    with library.database(root) as db:
        return view(_load(db))


def request(root, version):
    if parse(version) <= parse(__version__):
        raise ValueError(f"El servidor ya usa {__version__}.")
    device = library.device_state(root)
    if not device.get("updater") or age(device.get("heartbeat_at")) > 60:
        raise ValueError("El conector USB del Mac no está activo o no admite actualizaciones automáticas. "
                         "Actualiza el servidor una vez con el paquete para macOS.")
    if device.get("state") == "working":
        raise ValueError("Espera a que termine la copia USB antes de actualizar el servidor.")
    with library.database(root) as db:
        previous = view(_load(db))
        if previous and previous["state"] in {"requested", "running"}:
            raise ValueError(f"Ya hay una actualización a {previous['version']} en curso.")
        stamp = library.now()
        return _store(db, {"version": version, "state": "requested", "message": "Esperando al conector USB del Mac.",
                           "requested_at": stamp, "updated_at": stamp})


def claim(root, version):
    """Only one connector run takes a request; a second claim of the same request is refused."""
    with library.database(root) as db:
        value = view(_load(db))
        if not value or value["version"] != version or value["state"] != "requested":
            raise ValueError("No hay una actualización pendiente de esa versión.")
        return _store(db, {**value, "state": "running", "message": f"Descargando Prelo {version} en el Mac.",
                           "updated_at": library.now()})


def report(root, version, state, message):
    with library.database(root) as db:
        value = view(_load(db))
        if not value or value["version"] != version or value["state"] != "running":
            raise ValueError("No hay una actualización en marcha de esa versión.")
        return _store(db, {**value, "state": state, "message": message, "updated_at": library.now()})
