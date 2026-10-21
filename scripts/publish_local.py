"""Read selected Markdown files and create a local EPUB. Never alters the vault."""
import argparse
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
from margen.models import PublicationRequest
from margen.editor import plan_publication
from margen.epub import build_epub, clean_markdown

parser = argparse.ArgumentParser()
parser.add_argument("--vault", required=True, type=Path)
parser.add_argument("--output", required=True, type=Path)
parser.add_argument("--title", default="Lecturas en Prelo")
parser.add_argument("notes", nargs="+")
args = parser.parse_args()
vault = args.vault.resolve()
notes = []
for name in args.notes:
    file = (vault / name).resolve()
    if not file.is_relative_to(vault) or file.suffix.lower() != ".md":
        raise SystemExit("Cada nota debe ser un Markdown dentro del vault indicado.")
    text = file.read_text()
    heading = re.search(r"^# (.+)$", clean_markdown(text), re.M)
    notes.append({
        "id": str(uuid.uuid5(uuid.NAMESPACE_URL, name)), "path": name,
        "title": heading[1] if heading else file.stem, "markdown": text,
        "original_sha256": hashlib.sha256(text.encode()).hexdigest(),
    })
request = PublicationRequest(title=args.title, notes=notes)
edition = str(uuid.uuid4())
output = args.output / edition
record = build_epub(request, plan_publication(request), edition, output)
(output / "manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
print(output / record["filename"])
print(f"{len(record['sources'])} notas; {len(record['warnings'])} avisos de conversión. Sin IA.")
