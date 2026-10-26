"""Guided macOS service + USB installation, or plugin-only installation on desktop."""
import argparse
import json
import os
import secrets
import shutil
import socket
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from install_common import read_env, run, validate_connection, validate_vault, write_private
from install_plugin import install as install_plugin
from install_bridge import install as install_bridge
from install_usb import install as install_usb
import install_transaction

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_FILES = ("main.js", "manifest.json", "styles.css")


def request(base, route, token=None):
    headers = {"Authorization": "Bearer " + token} if token else {}
    with urllib.request.urlopen(urllib.request.Request(base + route, headers=headers), timeout=10) as response:
        return json.load(response)


def occupied(port):
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def fresh_build_context(folder):
    """Release archives give every file the same timestamp. BuildKit skips a file whose size and
    timestamp match its cached context, so an edit of the same length would keep the old code."""
    for path in Path(folder).rglob("*"):
        if path.is_file():
            os.utime(path)


def preflight(runtime, ai, root=ROOT):
    if sys.platform != "darwin":
        raise ValueError("El servicio USB requiere macOS. En Windows/Linux instala solo el plugin o usa BRAT.")
    for command in ["docker", "uv"]:
        if not shutil.which(command):
            raise ValueError(f"Falta {command}. Consulta los requisitos en docs/instalacion.md.")
    for name in PLUGIN_FILES:
        if not (Path(root) / "dist/margen" / name).is_file():
            raise ValueError("Descarga el paquete prelo-macos de Releases, que incluye el plugin compilado.")
    runtime = Path(runtime)
    env_file = runtime / "service.env"
    marker = runtime / "installation.json"
    if occupied(8765):
        if not marker.exists() or not env_file.exists():
            raise ValueError("El puerto 8765 ya está ocupado. Conserva esa instalación y usa --plugin-only --connection ARCHIVO.")
        env = read_env(env_file)
        try:
            request("http://127.0.0.1:8765", "/v1/status", env["MARGEN_TOKEN"])
        except Exception as exc:
            raise ValueError("El servicio que ocupa 8765 no coincide con esta instalación; no se modifica.") from exc
    if ai == "codex":
        if not shutil.which("codex"):
            raise ValueError("Instala Codex CLI y ejecuta codex login, o elige continuar sin IA.")
        help_text = run(["codex", "exec", "--help"], timeout=15).stdout
        if any(flag not in help_text for flag in ["--ignore-user-config", "--ignore-rules", "--ephemeral", "--output-schema"]):
            raise ValueError("Actualiza Codex CLI: faltan opciones necesarias para esta versión de Prelo.")
        login = run(["codex", "login", "status"], timeout=15, check=False)
        if login.returncode or "using ChatGPT" not in login.stdout + login.stderr:
            raise ValueError("Inicia sesión con codex login usando tu propia cuenta de ChatGPT.")
        if occupied(8766) and not marker.exists():
            raise ValueError("El puerto del puente (8766) está ocupado por otra instalación; no se modifica.")
    context = run(["docker", "context", "show"], timeout=10).stdout.strip()
    if marker.exists():
        previous = json.loads(marker.read_text(encoding="utf-8-sig"))
        if previous.get("docker_context") != context:
            raise ValueError("El contexto Docker cambió. Selecciona el contexto de la instalación original antes de actualizar.")
    docker = ["docker", "--context", context]
    run([*docker, "info", "--format", "{{.ServerVersion}}"], timeout=15)
    run([*docker, "compose", "version", "--short"], timeout=15)
    ids = run([*docker, "ps", "-aq", "--filter", "label=com.docker.compose.project=prelo"], timeout=15).stdout.split()
    if ids:
        if not marker.exists():
            raise ValueError("Ya existe un proyecto Docker llamado prelo; no se sustituye automáticamente.")
        containers = json.loads(run([*docker, "inspect", *ids], timeout=15).stdout)
        if any(m.get("Type") == "bind" for c in containers for m in c.get("Mounts", [])):
            raise ValueError("La instalación contiene montajes del equipo. No se iniciarán esos contenedores.")
    return context


def _install_service(vault, *, ai=None, root=ROOT, runtime=None, check=False):
    vault = validate_vault(vault)
    runtime = Path(runtime or Path.home() / "Library/Application Support/Prelo").resolve()
    env_file = runtime / "service.env"
    previous_env = read_env(env_file) if env_file.exists() else {}
    selected_ai = ai or ("codex" if previous_env.get("AI_PROVIDER") == "codex-bridge" else "none")
    context = preflight(runtime, selected_ai, root)
    version = json.loads((Path(root) / "manifest.json").read_text(encoding="utf-8-sig"))["version"]
    if check:
        print(f"Requisitos correctos. Vault: {vault}; versión {version}; modo {selected_ai}. No se ha instalado nada.")
        return
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    app = runtime / "app"
    if app.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = runtime / "backups" / stamp
        backup.mkdir(parents=True, mode=0o700)
        for name in ["service.env", ".env", "usb.json", "conexion-prelo.json", "installation.json"]:
            if (runtime / name).exists():
                shutil.copy2(runtime / name, backup / name)
        shutil.copytree(app, backup / "app")
    print("1/5 · Guardando la aplicación fuera de Documents…", flush=True)
    app.mkdir(exist_ok=True)
    if Path(root).resolve() != app.resolve():
        for name in ["server", "assets"]:
            shutil.copytree(Path(root) / name, app / name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns(".venv", "__pycache__", ".pytest_cache", "*.egg-info"))
        (app / "scripts").mkdir(exist_ok=True)
        for name in ["install.py", "install_common.py", "install_plugin.py", "install_bridge.py", "install_usb.py", "run_bridge.py", "install_transaction.py"]:
            shutil.copy2(Path(root) / "scripts" / name, app / "scripts" / name)
        for name in ["compose.yaml", "manifest.json"]:
            shutil.copy2(Path(root) / name, app / name)
        (app / "dist/margen").mkdir(parents=True, exist_ok=True)
        for name in PLUGIN_FILES:
            shutil.copy2(Path(root) / "dist/margen" / name, app / "dist/margen" / name)
    env = {**previous_env, "MARGEN_TOKEN": previous_env.get("MARGEN_TOKEN") or secrets.token_urlsafe(36),
           "MARGEN_BIND": previous_env.get("MARGEN_BIND", "127.0.0.1"), "MARGEN_PORT": "8765",
           "MARGEN_PUBLIC_URL": previous_env.get("MARGEN_PUBLIC_URL", "http://127.0.0.1:8765"),
           "AI_PROVIDER": "codex-bridge" if selected_ai == "codex" else "disabled",
           "CODEX_BRIDGE_URL": "http://host.docker.internal:8766"}
    if selected_ai == "codex":
        env["CODEX_BIN"] = shutil.which("codex")
    write_private(env_file, "".join(f"{k}={v}\n" for k, v in env.items()))
    marker = {"version": version, "docker_context": context, "state": "installing", "vault": str(vault)}
    write_private(runtime / "installation.json", json.dumps(marker, indent=2))
    print("2/5 · Preparando el conector nativo…", flush=True)
    install_bridge(runtime, env_file, root=app, label="local.prelo.codex-bridge", agent=selected_ai == "codex")
    if selected_ai == "none" and (Path.home() / "Library/LaunchAgents/local.prelo.codex-bridge.plist").exists():
        run(["launchctl", "bootout", f"gui/{os.getuid()}/local.prelo.codex-bridge"], timeout=15, check=False)
        (Path.home() / "Library/LaunchAgents/local.prelo.codex-bridge.plist").unlink()
    print("3/5 · Iniciando la biblioteca privada con volumen Docker…", flush=True)
    docker = ["docker", "--context", context]
    compose = [*docker, "compose", "--project-name", "prelo", "--project-directory", str(app),
               "--env-file", str(env_file), "--file", str(app / "compose.yaml")]
    fresh_build_context(app / "server")
    run([*compose, "up", "-d", "--build", "--wait", "--wait-timeout", "120", "margen"], timeout=420)
    container = run([*compose, "ps", "-q", "margen"], timeout=15).stdout.strip()
    if not container:
        raise RuntimeError("No aparece el contenedor del servicio.")
    run([*docker, "exec", container, "python", "-c", 'from pathlib import Path; Path("/data/.plugin-release").mkdir(exist_ok=True)'], timeout=15)
    run([*docker, "cp", str(app / "dist/margen") + "/.", container + ":/data/.plugin-release/"], timeout=30)
    request("http://127.0.0.1:8765", "/v1/status", env["MARGEN_TOKEN"])
    print("4/5 · Configurando la sincronización USB…", flush=True)
    install_usb(runtime, env_file, vault=vault, label="local.prelo.kobo")
    plugin_state = vault / ".obsidian/plugins/margen/data.json"
    settings = json.loads(plugin_state.read_text()).get("settings", {}) if plugin_state.exists() else {}
    usb_settings = json.loads((runtime / "usb.json").read_text())
    connection = {"serverUrl": "http://127.0.0.1:8765", "token": env["MARGEN_TOKEN"],
                  "outputFolder": settings.get("outputFolder", "Prelo/Publicaciones"),
                  "highlightsFolder": usb_settings["highlights_folder"]}
    write_private(runtime / "conexion-prelo.json", json.dumps(connection, indent=2))
    print("5/5 · Instalando el plugin…", flush=True)
    install_plugin(vault, root=app, connection=connection, enable=True)
    write_private(runtime / "installation.json", json.dumps({**marker, "state": "ready"}, indent=2))
    print("Prelo está listo. Abre Obsidian y activa los complementos de la comunidad si están restringidos.")
    print("Selecciona notas, prepara una revista y conecta el Kobo por USB a este Mac.")
    print("El archivo privado de conexión se ha guardado en Application Support/Prelo; no lo publiques.")


def backup_library(destination, token):
    import zipfile
    request = urllib.request.Request("http://127.0.0.1:8765/v1/backup", headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(request, timeout=300) as response:
        with destination.open("wb") as output:
            os.chmod(destination, 0o600)
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
    with zipfile.ZipFile(destination) as archive:
        if "catalogue.sql" not in archive.namelist() or archive.testzip():
            raise ValueError("El backup previo no es íntegro. La actualización no ha comenzado.")


def install_service(vault, *, ai=None, root=ROOT, runtime=None, check=False):
    if check:
        return _install_service(vault, ai=ai, root=root, runtime=runtime, check=True)
    vault = validate_vault(vault)
    runtime = Path(runtime or Path.home() / "Library/Application Support/Prelo").resolve()
    journal = runtime / "update-in-progress.json"
    if journal.exists():
        raise ValueError("Hay una instalación interrumpida. Ejecuta el instalador con --recover antes de continuar.")
    env = read_env(runtime / "service.env") if (runtime / "service.env").exists() else {}
    selected_ai = ai or ("codex" if env.get("AI_PROVIDER") == "codex-bridge" else "none")
    context = preflight(runtime, selected_ai, root)
    online = occupied(8765)
    if online:
        state = request("http://127.0.0.1:8765", "/v1/library", env["MARGEN_TOKEN"])
        if any(j.get("state") in {"running", "queued"} for j in state.get("jobs", [])) or state.get("device", {}).get("state") == "working":
            raise ValueError("Espera a que terminen la generación y el USB antes de actualizar. Cierra Obsidian en todos los equipos.")
    docker = ["docker", "--context", context]
    ids = run([*docker, "ps", "-aq", "--filter", "label=com.docker.compose.project=prelo",
               "--filter", "label=com.docker.compose.service=margen"], timeout=15).stdout.split()
    image = run([*docker, "inspect", "--format", "{{.Image}}", ids[0]], timeout=15).stdout.strip() if ids else ""
    backup = install_transaction.capture(runtime, vault, context, image)
    try:
        if online:
            backup_library(backup / "library.zip", env["MARGEN_TOKEN"])
    except BaseException:
        journal.unlink()  # No mutation has started; keep the snapshot for inspection.
        raise
    try:
        install_transaction.stop_agents()
        _install_service(vault, ai=selected_ai, root=root, runtime=runtime)
    except BaseException:
        try:
            install_transaction.recover(runtime)
        except Exception as error:
            raise RuntimeError("La actualización falló y la recuperación necesita revisión. Conserva el backup privado y ejecuta --recover.") from error
        raise
    journal.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path)
    parser.add_argument("--ai", choices=["none", "codex"])
    parser.add_argument("--plugin-only", action="store_true")
    parser.add_argument("--connection", type=Path)
    parser.add_argument("--recover", action="store_true", help="Recupera una instalación pública interrumpida desde su copia privada")
    parser.add_argument("--check", action="store_true", help="Comprueba requisitos sin instalar")
    args = parser.parse_args()
    if args.recover:
        install_transaction.recover(Path.home() / "Library/Application Support/Prelo")
        print("Instalación anterior recuperada. Abre Obsidian y comprueba la biblioteca.")
        return
    vault = args.vault
    if vault is None:
        if not sys.stdin.isatty():
            parser.error("Indica --vault /ruta/al/vault.")
        print("Prelo · instalación por USB\nCierra Obsidian antes de continuar.")
        vault = Path(input("Ruta del vault (la carpeta que contiene .obsidian): ").strip().strip("\"'"))
    if args.plugin_only:
        if args.check:
            validate_vault(vault)
            print("Vault válido; no se ha instalado nada.")
            return
        connection = validate_connection(json.loads(args.connection.read_text(encoding="utf-8-sig"))) if args.connection else None
        install_plugin(vault, connection=connection, enable=True)
        print("Plugin instalado. Abre Obsidian y conecta Prelo a tu servidor desde sus ajustes.")
    else:
        ai = args.ai
        if ai is None and sys.stdin.isatty():
            answer = input("¿Usar tu Codex CLI para IA? [s/N]: ").strip().lower()
            ai = "codex" if answer in {"s", "si", "sí"} else "none"
        install_service(vault, ai=ai, check=args.check)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, TimeoutError) as error:
        print(f"Instalación detenida: {error}", file=sys.stderr)
        raise SystemExit(1)
