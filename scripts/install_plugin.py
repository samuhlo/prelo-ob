"""Install a built plugin on any desktop OS, preserving its state and other plugins."""
import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from install_common import read_env, validate_connection, validate_vault, write_private

ROOT = Path(__file__).resolve().parents[1]


def install(vault, *, root=ROOT, connection=None, enable=False, second_brain=False):
    vault = validate_vault(vault)
    source = Path(root) / "dist/margen"
    manifest = json.loads((source / "manifest.json").read_text())
    if manifest["id"] != "margen":
        raise ValueError("Este paquete no es el plugin de Prelo.")
    files = {name: (source / name).read_bytes() for name in ["main.js", "manifest.json", "styles.css"]}
    if (source / "sql-wasm.wasm").is_file():
        files["sql-wasm.wasm"] = (source / "sql-wasm.wasm").read_bytes()
    target = vault / ".obsidian/plugins/margen"
    if target.is_symlink():
        raise ValueError("La carpeta del plugin no puede ser un enlace simbólico.")
    config = target / "data.json"
    previous = config.read_bytes() if config.exists() else None
    state = json.loads(previous) if previous else {"settings": {}, "sources": {}}
    if not isinstance(state, dict) or not isinstance(state.get("settings", {}), dict):
        raise ValueError("La configuración existente no se reconoce; se conserva.")
    settings = state.setdefault("settings", {})
    if connection is not None:
        settings.update(validate_connection(connection))
    elif previous is None:
        env = read_env(Path(root) / ".env") if (Path(root) / ".env").exists() else {}
        settings.update({"serverUrl": "http://127.0.0.1:8765", "token": env.get("MARGEN_TOKEN", "")})
        if second_brain:
            settings.update(outputFolder="99_Recursos/adjuntos/Margen", highlightsFolder="02_Cerebro/Media_&_Consumo/Subrayados_Kobo")
    enabled_path = vault / ".obsidian/community-plugins.json"
    enabled = json.loads(enabled_path.read_text()) if enabled_path.exists() else []
    if not isinstance(enabled, list):
        raise ValueError("No se reconoce la lista de plugins; se conserva.")
    if target.exists() or enable and enabled_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup = Path(root) / "data/plugin-backups" / stamp
        backup.mkdir(parents=True, mode=0o700)
        if target.exists():
            shutil.copytree(target, backup / "margen")
        if enabled_path.exists():
            shutil.copy2(enabled_path, backup / "community-plugins.json")
    target.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        write_private(target / name, content, mode=0o644)
    if previous is None or connection is not None:
        if config.exists() and config.read_bytes() != previous:
            raise ValueError("Obsidian cambió su configuración durante la instalación. Cierra Obsidian y repite.")
        write_private(config, json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    if enable and "margen" not in enabled:
        enabled.append("margen")
        write_private(enabled_path, json.dumps(enabled, indent=2) + "\n")
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vault", type=Path)
    parser.add_argument("--connection", type=Path, help="Archivo privado conexion-prelo.json")
    parser.add_argument("--enable", action="store_true")
    parser.add_argument("--second-brain", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    connection = json.loads(args.connection.read_text()) if args.connection else None
    target = install(args.vault, connection=connection, enable=args.enable, second_brain=args.second_brain)
    print(f"Prelo instalado en {target}. Abre Obsidian y activa Prelo en Complementos de la comunidad.")


if __name__ == "__main__":
    main()
