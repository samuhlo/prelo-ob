"""Update the Mac service from a verified GitHub release, in its own launchd job.

The USB connector downloads and checks the package, then hands over: the update command
restarts the connector itself, so it cannot run inside the connector's job."""
import argparse
import hashlib
import io
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

DOWNLOADS = "https://github.com/samuhlo/prelo-ob/releases/download/"
VERSION = re.compile(r"(0|[1-9]\d{0,3})\.(0|[1-9]\d{0,3})\.(0|[1-9]\d{0,3})")
LABEL = "local.prelo.update"
PACKAGE_LIMIT = 200 * 1024 * 1024


def download(url, limit=PACKAGE_LIMIT):
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read(limit + 1)
    except urllib.error.HTTPError as error:
        raise ValueError("No se encontró ese paquete en las releases de Prelo." if error.code == 404
                         else "GitHub no respondió al descargar la actualización.") from None
    if len(data) > limit:
        raise ValueError("El paquete de la release es demasiado grande.")
    return data


def fetch(version, folder, get=download):
    """Download prelo-macos for that release and unpack it only if SHA256SUMS vouches for it."""
    if not VERSION.fullmatch(version):
        raise ValueError("Versión no válida.")
    base = DOWNLOADS + version + "/"
    name = f"prelo-macos-{version}.zip"
    sums = {}
    for line in get(base + "SHA256SUMS", 64 * 1024).decode().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})\s+\*?(\S+)", line.strip())
        if match:
            sums[match[2]] = match[1]
    if name not in sums:
        raise ValueError("La release no incluye el paquete para macOS.")
    data = get(base + name)
    if hashlib.sha256(data).hexdigest() != sums[name]:
        raise ValueError("La descarga no coincide con la release. No se ha cambiado nada.")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    target, partial = folder / f"prelo-{version}", folder / f".prelo-{version}.partial"
    for path in (target, partial):
        if path.exists():
            shutil.rmtree(path)
    prefix = f"prelo-{version}"
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            parts = PurePosixPath(info.filename).parts
            if len(parts) < 2 or parts[0] != prefix or any(p in {"", ".", ".."} for p in parts) or info.filename.startswith("/"):
                raise ValueError("El paquete contiene rutas no válidas.")
            if info.is_dir():
                continue
            destination = partial.joinpath(*parts[1:])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(info))
            destination.chmod(0o755 if (info.external_attr >> 16) & 0o111 else 0o644)
    manifest = json.loads((partial / "manifest.json").read_text(encoding="utf-8-sig"))
    if manifest.get("id") != "margen" or manifest.get("version") != version:
        shutil.rmtree(partial)
        raise ValueError("El paquete no corresponde a esa versión de Prelo.")
    partial.rename(target)
    return target


def launch(config_path, release, version):
    """Start the update as a one-off job outside LaunchAgents, so it never runs again at login."""
    config_path = Path(config_path).resolve()
    runtime = config_path.parent
    (runtime / "logs").mkdir(exist_ok=True)
    plist = runtime / "updates/update.plist"
    log = str(runtime / "logs/update.log")
    plist.write_bytes(plistlib.dumps({
        "Label": LABEL, "RunAtLoad": True, "WorkingDirectory": str(runtime),
        "ProgramArguments": [sys.executable, "-m", "margen.updater", "--config", str(config_path),
                             "--release", str(release), "--version", version],
        "EnvironmentVariables": {"PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")},
        "StandardOutPath": log, "StandardErrorPath": log}))
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{domain}/{LABEL}"], capture_output=True, timeout=15)
    for attempt in range(4):
        result = subprocess.run(["launchctl", "bootstrap", domain, str(plist)], capture_output=True, timeout=15)
        if result.returncode == 0:
            return
        time.sleep(1)
    raise ValueError("macOS no permitió iniciar la actualización.")


def api(config, route, body=None):
    request = urllib.request.Request(config["server_url"].rstrip("/") + route,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + config["token"], "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def serving(config, version, seconds=300):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if api(config, "/health").get("version") == version:
                return True
        except (OSError, ValueError):
            pass
        time.sleep(5)
    return False


def say(text):
    print(datetime.now(timezone.utc).isoformat(timespec="seconds"), text, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--release", type=Path, required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if not VERSION.fullmatch(args.version):
        raise SystemExit("Versión no válida.")
    command = [part.replace("{release}", str(args.release)).replace("{version}", args.version)
               for part in config["update_command"]]
    say(f"Actualizando el servicio a {args.version}.")
    try:
        api(config, "/v1/service/update/report", {"version": args.version, "state": "running",
            "message": f"Instalando Prelo {args.version}. El servicio se reiniciará en unos minutos."})
    except (OSError, ValueError):
        pass
    try:
        code = subprocess.run(command, timeout=45 * 60).returncode
    except subprocess.TimeoutExpired:
        code = "tiempo agotado"
    if code == 0 and serving(config, args.version):
        say("Servicio actualizado.")
        shutil.rmtree(args.release, ignore_errors=True)
        return
    say(f"La actualización falló ({code}).")
    # Both update paths restore the previous service on failure; report through whichever one answers.
    try:
        api(config, "/v1/service/update/report", {"version": args.version, "state": "failed",
            "message": "La actualización del servidor no terminó. Revisa logs/update.log en el Mac."})
    except (OSError, ValueError):
        pass
    raise SystemExit(1)


if __name__ == "__main__":
    main()
