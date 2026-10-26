import hashlib
import re
from pathlib import PurePosixPath
from urllib.parse import unquote
from .epub import normalize
from .models import Highlight


def resolve(highlight: Highlight, publications: dict):
    volume = unquote(highlight.volume_id)
    match = re.search(r"margen-([0-9a-f-]{36})\.epub$", volume)
    publication = publications.get(match.group(1)) if match else None
    source = None
    method = "book"
    if publication:
        location = unquote(highlight.content_id + " " + highlight.start_path)
        candidates = [s for s in publication["sources"] if PurePosixPath(s["href"]).name in location]
        anchored = [s for s in candidates or publication["sources"] if re.search(
            r"(?<![\w-])(?:" + re.escape(s.get("anchor", "n_" + s["id"])) + r"|b_" + re.escape(s["id"]) + r"_\d+)(?=$|[^\w.-])", location)]
        if len(anchored) == 1:
            source, method = anchored[0], "anchor"
        elif len(candidates) == 1:
            source, method = candidates[0], "chapter"
        elif highlight.text.strip():
            # Short notes can share a file: search the quote among them first.
            quote = normalize(highlight.text)
            candidates = [s for s in candidates or publication["sources"] if quote in s["text"]]
            if len(candidates) == 1:
                source, method = candidates[0], "exact_text"
        if not source:
            method = "unresolved"
    key = hashlib.sha256((highlight.volume_id + "\0" + highlight.id).encode()).hexdigest()
    content_note = ""
    if publication and publication.get("writing_mode", "original") != "original":
        content_note = "Subrayado de una adaptación con IA; puede no coincidir literalmente con la nota original."
    elif publication and publication.get("study_aids", "none") != "none":
        content_note = "Esta edición conserva las notas originales e incluye apoyos de estudio generados con IA."
    return {
        "content_note": content_note,
        **highlight.model_dump(), "key": key, "match": method,
        "publication_id": publication["id"] if publication else None,
        "publication_title": publication["title"] if publication else highlight.title,
        "source": {k: source[k] for k in ["id", "path", "title", "sha256"]} if source else None,
    }
