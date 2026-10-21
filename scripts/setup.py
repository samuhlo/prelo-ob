"""Prepare local credentials without printing secrets or replacing existing settings."""
import secrets
from pathlib import Path

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    print(".env ya existe; se conserva.")
else:
    example = (root / ".env.example").read_text()
    with target.open("x") as file:
        file.write(example.replace("replace-with-a-long-random-token", secrets.token_urlsafe(36)))
    target.chmod(0o600)
    print(".env creado con credencial local. Configura ahí el proveedor de IA cuando quieras.")
