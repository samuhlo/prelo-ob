"""Run with server/.venv/bin/python scripts/run_bridge.py."""
import os
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "server"))
for line in (root / ".env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        os.environ[k] = v
import uvicorn
uvicorn.run("margen.bridge:app", host="127.0.0.1", port=8766, access_log=False)
