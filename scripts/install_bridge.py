"""Prepare the native Python runtime and optionally install the personal Codex bridge."""
import argparse
import os
import plistlib
import shutil
import sys
from pathlib import Path
from install_common import load_agent, read_env, run, write_private

ROOT = Path(__file__).resolve().parents[1]


def install(runtime, env_file, *, label="local.margen.codex-bridge", agent=True, root=ROOT):
    if sys.platform != "darwin":
        raise ValueError("El conector nativo de esta versión requiere macOS.")
    runtime = Path(runtime).expanduser().resolve()
    env = read_env(env_file)
    (runtime / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(root) / "scripts/run_bridge.py", runtime / "scripts/run_bridge.py")
    python = runtime / "server/.venv/bin/python"
    if not python.exists():
        run(["uv", "venv", "--python", "3.13", python.parent.parent], timeout=240)
    run(["uv", "pip", "install", "--python", python, "-r", Path(root) / "server/requirements.lock"], timeout=240)
    run(["uv", "pip", "install", "--python", python, "--no-deps", "--reinstall-package", "margen-server", Path(root) / "server"], timeout=180)
    values = {k: v for k, v in env.items() if k in {"MARGEN_TOKEN", "AI_MODEL", "CODEX_BIN", "AI_CONCURRENCY", "AI_TIMEOUT"}}
    write_private(runtime / ".env", "".join(f"{k}={v}\n" for k, v in values.items()))
    if not agent:
        return python
    logs = runtime / "logs"
    logs.mkdir(exist_ok=True)
    path = Path.home() / "Library/LaunchAgents" / (label + ".plist")
    config = {"Label": label, "ProgramArguments": [str(python), str(runtime / "scripts/run_bridge.py")],
              "WorkingDirectory": str(runtime), "EnvironmentVariables": {"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
              "RunAtLoad": True, "KeepAlive": True,
              "StandardOutPath": str(logs / "bridge.log"), "StandardErrorPath": str(logs / "bridge-error.log")}
    write_private(path, plistlib.dumps(config))
    load_agent(label, path)
    return python


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=Path.home() / "Library/Application Support/Margen")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--label", default="local.margen.codex-bridge")
    parser.add_argument("--no-agent", action="store_true")
    args = parser.parse_args()
    install(args.runtime, args.env_file, label=args.label, agent=not args.no_agent)
    print("Entorno nativo preparado." if args.no_agent else "Puente de Codex instalado.")


if __name__ == "__main__":
    main()
