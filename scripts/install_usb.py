"""Install USB automation on macOS for an explicitly selected Obsidian vault."""
import argparse
import json
import os
import plistlib
import sys
from pathlib import Path
from install_common import load_agent, read_env, relative_folder, validate_vault, write_private

ROOT = Path(__file__).resolve().parents[1]


def install(runtime, env_file, *, vault=None, folder=None, server_url=None, label="local.margen.kobo"):
    if sys.platform != "darwin":
        raise ValueError("La automatización USB de esta versión requiere macOS.")
    runtime = Path(runtime).expanduser().resolve()
    python = runtime / "server/.venv/bin/python"
    if not python.is_file():
        raise ValueError("Prepara primero el entorno con scripts/install_bridge.py.")
    config_path = runtime / "usb.json"
    config = json.loads(config_path.read_text(encoding="utf-8-sig")) if config_path.exists() else {}
    selected = vault or config.get("vault")
    if not selected:
        raise ValueError("Indica el vault con --vault /ruta/al/vault.")
    config.update(vault=str(validate_vault(selected)),
                  highlights_folder=relative_folder(folder or config.get("highlights_folder", "Prelo/Subrayados")),
                  server_url=server_url or config.get("server_url", "http://127.0.0.1:8765"),
                  token=read_env(env_file)["MARGEN_TOKEN"])
    config.setdefault("state", str(runtime / "usb-state"))
    config.setdefault("auto_eject", True)
    write_private(config_path, json.dumps(config, indent=2) + "\n")
    logs = runtime / "logs"
    logs.mkdir(exist_ok=True)
    path = Path.home() / "Library/LaunchAgents" / (label + ".plist")
    config = {"Label": label, "ProgramArguments": [str(python), "-m", "margen.native", "--config", str(config_path)],
              "WorkingDirectory": str(runtime), "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 15,
              "EnvironmentVariables": {"PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")},
              "StandardOutPath": str(logs / "kobo.log"), "StandardErrorPath": str(logs / "kobo-error.log")}
    write_private(path, plistlib.dumps(config))
    load_agent(label, path)
    return config_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path)
    parser.add_argument("--highlights-folder")
    parser.add_argument("--server-url")
    parser.add_argument("--runtime", type=Path, default=Path.home() / "Library/Application Support/Margen")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--label", default="local.margen.kobo")
    args = parser.parse_args()
    install(args.runtime, args.env_file, vault=args.vault, folder=args.highlights_folder,
            server_url=args.server_url, label=args.label)
    print("Conector USB instalado. Funciona con Obsidian cerrado después de iniciar la sesión del Mac.")


if __name__ == "__main__":
    main()
