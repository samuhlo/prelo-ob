"""Read the images of old notes and redraw or describe them in the magazine's style."""
import base64
import io
import re
import threading
from concurrent.futures import ThreadPoolExecutor
import os
from PIL import Image
from pydantic import ValidationError
from .diagrams import render_diagram
from .models import Figure, ImageReading, ImageReadings, PublicationRequest

IMAGE = re.compile(r"!\[([^\]]*)\]\(margen-asset:([\w-]+)\)")
BATCH = 6
ORIGINAL = {"es": "Ver la imagen original", "gl": "Ver a imaxe orixinal"}


def vision_png(asset) -> str:
    """Uniform PNG input for every provider, at most 1600 px on its long side."""
    with Image.open(io.BytesIO(base64.b64decode(asset.data))) as image:
        image.load()
        image = image.convert("RGB")
        image.thumbnail((1600, 1600))
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
    return base64.b64encode(output.getvalue()).decode()


def context(markdown: str, match) -> tuple[str, str]:
    before = IMAGE.sub("", markdown[:match.start()]).strip()[-500:]
    after = IMAGE.sub("", markdown[match.end():]).strip()[:500]
    return before, after


def decide(reading: ImageReading, style: str) -> Figure | None:
    """Only confident readings replace an original; anything doubtful keeps the image."""
    common = {"asset_id": reading.asset_id, "description": reading.description.strip(),
              "caption": reading.caption.strip()}
    if reading.kind == "decorative" and reading.confidence == "high":
        return Figure(action="remove", **common)
    confident = reading.confidence in {"high", "medium"}
    if reading.kind == "diagram" and confident and render_diagram(reading.diagram, style):
        return Figure(action="diagram", diagram=reading.diagram, **common)
    if reading.kind in {"table", "formula"} and confident and reading.table_markdown.strip():
        return Figure(action="table", table_markdown=reading.table_markdown.strip(), **common)
    if common["description"]:
        return Figure(action="caption", **common)
    return None


def apply_figures(markdown: str, figures: list[Figure], language: str) -> str:
    """Replace each original image reference according to its figure decision."""
    by_id = {f.asset_id: f for f in figures}
    def replace(match):
        figure = by_id.get(match.group(2))
        if not figure:
            return match.group(0)
        alt = figure.description.replace("[", "(").replace("]", ")").replace("\n", " ")
        original = f"[{ORIGINAL[language]}](margen-original:{figure.asset_id})"
        caption = f"*{figure.caption}*" if figure.caption else ""
        footer = f"{caption}  \n{original}" if caption else original
        if figure.action == "remove":
            return ""
        if figure.action == "diagram":
            return f"![{alt}](margen-figure:{figure.asset_id})\n\n{footer}"
        if figure.action == "table":
            return f"\n\n{figure.table_markdown}\n\n{footer}"
        return f"![{alt}](margen-asset:{figure.asset_id})" + (f"\n\n{caption}" if caption else "")
    return IMAGE.sub(replace, markdown)


def read_images(request: PublicationRequest, cache, progress, instructions: str, schema: dict) -> list[Figure]:
    assets = {a.id: a for a in request.assets}
    batches = []
    for note in request.notes:
        found = [(m, context(note.markdown, m)) for m in IMAGE.finditer(note.markdown) if m.group(2) in assets]
        unique = list({m.group(2): (m, c) for m, c in found}.values())
        for i in range(0, len(unique), BATCH):
            batches.append((note, unique[i:i + BATCH]))
    if not batches:
        return []
    total = sum(len(items) for _, items in batches)
    done, lock, failures = [0], threading.Lock(), []

    def run(batch):
        note, items = batch
        payload = {"language": request.language, "note_title": note.title, "images": [
            {"order": n, "asset_id": m.group(2), "alt": m.group(1), "text_before": before, "text_after": after}
            for n, (m, (before, after)) in enumerate(items, 1)]}
        images = [{"media_type": "image/png", "data": vision_png(assets[m.group(2)])} for m, _ in items]
        readings = []
        for _ in range(2):
            try:
                result = ImageReadings.model_validate(cache.call("vision", instructions, payload, schema, images))
            except ValidationError:
                cache.forget("vision", instructions, payload, schema)
                continue
            except ValueError as exc:
                failures.append(exc)
                continue
            expected = {m.group(2) for m, _ in items}
            readings = [r for r in result.images if r.asset_id in expected]
            break
        with lock:
            done[0] += len(items)
            progress(f"Leyendo imágenes: {done[0]} de {total}.")
        # An image that could not be read keeps its original; it never blocks the edition.
        return [f for f in (decide(r, request.style) for r in readings) if f]

    progress(f"Leyendo imágenes: 0 de {total}.")
    workers = max(1, int(os.getenv("AI_CONCURRENCY", "2")))
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="margen-vision") as pool:
        results = list(pool.map(run, batches))
    if failures and len(failures) >= 2 * len(batches):
        # Nothing could be read: a provider problem, not a doubtful image.
        raise failures[0]
    figures = [f for result in results for f in result]
    return list({f.asset_id: f for f in figures}.values())
