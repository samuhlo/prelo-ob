"""Shared installer helpers; no credentials are printed."""
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit


def read_env(path):
    return dict(line.split("=", 1) for line in Path(path).read_text().splitlines()
                if "=" in line and not line.lstrip().startswith("#"))


def write_private(path, content, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content.encode() if isinstance(content, str) else content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def validate_vault(value):
    vault = Path(value).expanduser().resolve()
    if not (vault / ".obsidian").is_dir():
        raise ValueError("Selecciona la carpeta de un vault que ya hayas abierto en Obsidian.")
    return vault


def relative_folder(value):
    parts = value.replace("\\", "/").split("/")
    if not parts or any(not p or p.startswith(".") or ":" in p for p in parts):
        raise ValueError("La carpeta debe ser relativa al vault, sin rutas ocultas ni '..'.")
    return "/".join(parts)


def validate_connection(value):
    url = value.get("serverUrl", "").rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("La dirección del servidor no es válida.")
    token = value.get("token")
    if not isinstance(token, str) or len(token) < 24 or "\n" in token or "\r" in token:
        raise ValueError("La conexión necesita una credencial de al menos 24 caracteres.")
    result = {"serverUrl": url, "token": token}
    for name in ["outputFolder", "highlightsFolder"]:
        if name in value:
            result[name] = relative_folder(value[name])
    return result


def run(args, timeout=60, check=True):
    try:
        result = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{Path(str(args[0])).name} superó {timeout} segundos; la operación se ha detenido.") from exc
    if check and result.returncode:
        raise RuntimeError(f"Falló {Path(str(args[0])).name} (código {result.returncode}). Consulta docs/instalacion.md.")
    return result


def load_agent(label, path):
    if not re.fullmatch(r"local\.[a-zA-Z0-9.-]+", label):
        raise ValueError("Identificador de agente no válido.")
    run(["launchctl", "bootout", f"gui/{os.getuid()}/{label}"], timeout=15, check=False)
    for attempt in range(4):
        result = run(["launchctl", "bootstrap", f"gui/{os.getuid()}", path], timeout=15, check=False)
        if result.returncode == 0:
            return
        if result.returncode != 5 or attempt == 3:
            raise RuntimeError("No se pudo registrar el agente de inicio de sesión.")
        time.sleep(1)
