"""Validate EPUB with EPUBCheck in an isolated container, WITHOUT host mounts."""
import argparse
import json
import subprocess
import uuid
from pathlib import Path

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("epub", type=Path)
parser.add_argument("--checker", type=Path, default=root / "data/validation/epubcheck-5.4.0")
args = parser.parse_args()
if not args.epub.is_file() or not (args.checker / "epubcheck.jar").is_file():
    raise SystemExit("Se necesita un EPUB y una distribución local de EPUBCheck (--checker).")
name = "margen-epubcheck-" + uuid.uuid4().hex[:10]


def docker(*argv, timeout=30, check=True):
    return subprocess.run(["docker", *argv], capture_output=True, text=True, timeout=timeout, check=check)


created = False
try:
    docker("create", "--name", name, "--network", "none",
           "--label", "local.margen.purpose=epub-validation",
           "eclipse-temurin:21-jre", "java", "-jar", "/checker/epubcheck.jar", "/book.epub")
    created = True
    # docker cp streams from the client; the VM is never given a host directory.
    docker("cp", str(args.checker.resolve()), name + ":/checker")
    docker("cp", str(args.epub.resolve()), name + ":/book.epub")
    result = docker("start", "-a", name, timeout=45, check=False)
    print(result.stdout + result.stderr, end="")
    state = json.loads(docker("inspect", "--format", "{{json .State}}", name).stdout)
    raise SystemExit(state["ExitCode"])
except subprocess.TimeoutExpired:
    raise SystemExit("La validación excedió el tiempo de espera. No se han usado montajes del equipo.")
except subprocess.CalledProcessError as exc:
    raise SystemExit(exc.stderr.strip() or "Docker no pudo completar la validación.")
finally:
    if created:
        try:
            docker("rm", "-f", name, timeout=8, check=False)
        except subprocess.TimeoutExpired:
            print(f"Limpieza pendiente del contenedor de prueba {name}.")
