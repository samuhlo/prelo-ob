"""Staged editorial pipeline: a compact plan, then one call per chunk of each note."""
import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
from pydantic import BaseModel, ValidationError
from .models import EditorialPlan, Chapter, PublicationRequest, Outline, WrittenPart, EditedArticle
from .prompts import outline_instructions, write_instructions

DEFAULT_SUBTITLE = {"es": "Una selección de tu biblioteca personal", "gl": "Unha selección da túa biblioteca persoal"}
# Below this total the planner reads every note in full; above it, a digest of each.
FULL_OUTLINE_LIMIT = 60_000
CACHE_DAYS = 30


def strict_schema(model: type[BaseModel]):
    schema = model.model_json_schema()
    for definition in [schema, *schema.get("$defs", {}).values()]:
        if definition.get("type") == "object":
            definition["additionalProperties"] = False
            definition["required"] = list(definition["properties"])
    return schema


def ai_available():
    if os.getenv("AI_PROVIDER") == "disabled":
        return False
    if os.getenv("AI_PROVIDER") == "codex-bridge":
        return bool(os.getenv("CODEX_BRIDGE_URL"))
    if os.getenv("AI_PROVIDER") == "codex-cli":
        import shutil
        return bool(shutil.which(os.getenv("CODEX_BIN", "codex")))
    return bool(os.getenv("AI_BASE_URL") and os.getenv("AI_MODEL"))


def stage_settings(stage: str):
    """Model and reasoning effort per stage, e.g. AI_MODEL_PLAN / AI_EFFORT_WRITE."""
    model = os.getenv(f"AI_MODEL_{stage.upper()}") or os.getenv("AI_MODEL", "")
    effort = os.getenv(f"AI_EFFORT_{stage.upper()}") or os.getenv("AI_EFFORT", "")
    return model, effort


def timeout():
    return int(os.getenv("AI_TIMEOUT", "600"))


def complete(stage: str, instructions: str, payload: dict, schema: dict) -> dict:
    model, effort = stage_settings(stage)
    provider = os.getenv("AI_PROVIDER")
    if provider == "codex-cli":
        from .codex_editor import codex_complete
        return codex_complete(instructions, payload, schema, model, effort, timeout())
    if provider == "codex-bridge":
        try:
            with httpx.Client(timeout=timeout() + 30, follow_redirects=False) as client:
                response = client.post(os.environ["CODEX_BRIDGE_URL"].rstrip("/") + "/v1/complete",
                    headers={"Authorization": "Bearer " + os.environ["MARGEN_TOKEN"]},
                    json={"instructions": instructions, "input": payload, "output_schema": schema,
                          "model": model, "effort": effort})
                if response.status_code == 404:
                    raise ValueError("El puente de Codex del Mac es de una versión anterior. Actualiza Prelo en el Mac.")
                if response.status_code == 422:
                    raise ValueError(response.json().get("detail", "Codex no pudo preparar la edición."))
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise ValueError("El puente de Codex del Mac no responde. Inicia «python scripts/run_bridge.py».") from exc
    body = {
        "model": model,
        "messages": [{"role": "system", "content": instructions},
                     {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        "response_format": {"type": "json_schema", "json_schema": {
            "name": stage, "strict": True, "schema": schema,
        }},
    }
    if effort:
        body["reasoning_effort"] = effort
    headers = {}
    if os.getenv("AI_API_KEY"):
        headers["Authorization"] = "Bearer " + os.environ["AI_API_KEY"]
    try:
        with httpx.Client(timeout=timeout(), follow_redirects=False) as client:
            response = client.post(os.environ["AI_BASE_URL"].rstrip("/") + "/chat/completions",
                                   json=body, headers=headers)
            response.raise_for_status()
            result = response.json()
        choice = result["choices"][0]
        if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
            raise ValueError("La IA no devolvió una propuesta completa. Inténtalo de nuevo.")
        return json.loads(choice["message"]["content"])
    except (httpx.HTTPError, KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        # Do not disclose provider responses containing credentials or private notes.
        raise ValueError("No se pudo obtener una propuesta de IA. Revisa el proveedor, modelo y conexión.") from exc


class Cache:
    """Completed stages survive a failed edition, so a retry does not spend the quota twice."""

    def __init__(self, directory: Path | None):
        self.directory = directory
        if directory:
            directory.mkdir(parents=True, exist_ok=True)
            limit = time.time() - CACHE_DAYS * 86400
            for path in directory.glob("*.json"):
                if path.stat().st_mtime < limit:
                    path.unlink(missing_ok=True)

    def call(self, stage, instructions, payload, schema):
        key = hashlib.sha256(json.dumps([stage_settings(stage), instructions, payload, schema],
                                        ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        path = self.directory / f"{key}.json" if self.directory else None
        if path and path.exists():
            return json.loads(path.read_text())
        result = complete(stage, instructions, payload, schema)
        if path:
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(result, ensure_ascii=False))
            temporary.replace(path)
        return result

    def forget(self, stage, instructions, payload, schema):
        if self.directory:
            key = hashlib.sha256(json.dumps([stage_settings(stage), instructions, payload, schema],
                                            ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            (self.directory / f"{key}.json").unlink(missing_ok=True)


def body_of(markdown: str) -> str:
    from .epub import clean_markdown
    return clean_markdown(markdown)


def blocks(text: str):
    """Paragraph-level blocks; a fenced code block is never split."""
    result, current, fence = [], [], None
    for line in text.splitlines():
        marker = re.match(r"\s*(```|~~~)", line)
        if marker:
            fence = None if fence == marker.group(1) else fence or marker.group(1)
        if not line.strip() and fence is None and current:
            result.append("\n".join(current))
            current = []
        elif line.strip() or current:
            current.append(line)
    if current:
        result.append("\n".join(current))
    return result


def sentences(block: str, limit: int) -> list[str]:
    pieces, current = [], ""
    for sentence in re.split(r"(?<=[.!?:;])\s+", block):
        if current and len(current) + len(sentence) + 1 > limit:
            pieces.append(current)
            current = ""
        current = f"{current} {sentence}" if current else sentence
    return pieces + [current] if current else pieces


def split_markdown(text: str, limit: int) -> list[str]:
    """Chunks under limit, cut before a heading when possible, never inside code.
    A heading always travels with the text that follows it."""
    pieces = []
    for block in blocks(text):
        fenced = block.lstrip().startswith(("```", "~~~"))
        pieces.extend(sentences(block, limit) if len(block) > limit and not fenced else [block])
    chunks, current, size = [], [], 0
    is_heading = lambda b: b.lstrip().startswith("#")
    for block in pieces:
        if current and not all(map(is_heading, current)) and (
                size + len(block) > limit or is_heading(block) and size > limit * 0.6):
            carried = []
            while current and is_heading(current[-1]):
                carried.insert(0, current.pop())
            chunks.append("\n\n".join(current))
            current, size = carried, sum(len(b) + 2 for b in carried)
        current.append(block)
        size += len(block) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks or [""]


def digest(note, full: bool):
    text = body_of(note.markdown)
    entry = {"id": note.id, "title": note.title, "path": note.path, "characters": len(text),
             "images": text.count("margen-asset:")}
    if full:
        return {**entry, "markdown": text}
    headings = [b.strip() for b in blocks(text) if re.match(r"#{1,3} ", b.strip()) and "\n" not in b.strip()]
    return {**entry, "headings": headings[:40], "beginning": text[:1500]}


TOKEN = re.compile(r"margen-asset:[\w-]+|\d[\d.:/]*\d|`[^`\n]{2,80}`")


def required_tokens(source: str) -> set[str]:
    """Literal items a faithful rewrite or translation must keep: data, code and images."""
    # The H1 repeats the article title, which the layout already shows.
    source = re.sub(r"^# .*$", "", source, flags=re.M)
    # Long unbroken strings are base64 blobs or hashes pasted by accident, not data to keep.
    source = re.sub(r"\S{60,}", " ", source)
    tokens = {t.strip("`") for t in TOKEN.findall(source)}
    # Commands must survive verbatim; untagged blocks are often tables pasted from
    # a PDF and may become a translated table, so only their data is required.
    for block in re.findall(r"```[ \t]*[\w+-]+[^\n]*\n(.*?)```", source, re.S):
        tokens.update(" ".join(line.split()) for line in block.splitlines() if len(line.strip()) >= 4)
    return {t for t in tokens if t}


def missing_tokens(source: str, written: str) -> list[str]:
    flat = " ".join(written.split())
    return sorted(t for t in required_tokens(source) if t not in flat)


def make_outline(request: PublicationRequest, cache: Cache):
    full = sum(len(n.markdown) for n in request.notes) <= FULL_OUTLINE_LIMIT
    payload = {
        "title": request.title, "intent": request.intent, "style": request.style, "artwork": request.artwork,
        "writing_mode": request.writing_mode, "study_aids": request.study_aids,
        "language": request.language, "preserve_order": request.preserve_order,
        "notes": [digest(n, full) for n in request.notes],
    }
    instructions, schema = outline_instructions(request), strict_schema(Outline)
    error = None
    for attempt in range(2):
        attempt_payload = {**payload, "previous_error": str(error)} if error else payload
        result = cache.call("plan", instructions, attempt_payload, schema)
        try:
            outline = Outline.model_validate(result)
            EditorialPlan(**outline.model_dump(exclude={"briefs"})).verify_outline(request)
            return outline
        except (ValidationError, ValueError) as exc:
            cache.forget("plan", instructions, attempt_payload, schema)
            error = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else exc
    raise ValueError(f"La IA no preparó un plan válido: {error}")


class Writer:
    """Writes the parts of one note at a time, so each note starts as soon as it is ready."""

    def __init__(self, request: PublicationRequest, outline: Outline, cache: Cache):
        self.request, self.cache = request, cache
        self.briefs = {b.source_id: b for b in outline.briefs}
        self.notes = {n.id: n for n in request.notes}
        self.chapter_of = {i: c.title for c in outline.chapters for i in c.source_ids}
        self.plan_view = {"title": outline.title, "subtitle": outline.subtitle, "chapters": [
            {"title": c.title, "notes": [{"id": i, "title": self.notes[i].title,
                                          "summary": self.briefs[i].summary if i in self.briefs else ""}
                                         for i in c.source_ids]}
            for c in outline.chapters]}
        self.instructions, self.schema = write_instructions(request), strict_schema(WrittenPart)
        self.check = request.writing_mode not in {"original", "review"}

    def tasks(self, note):
        """(source_id, source part, payload) for every part of the note, as the writer will read it."""
        parts = split_markdown(body_of(note.markdown), chunk_limit())
        brief = self.briefs.get(note.id)
        return [(note.id, part, {
            "settings": {"writing_mode": self.request.writing_mode, "study_aids": self.request.study_aids,
                         "language": self.request.language, "intent": self.request.intent},
            "publication": self.plan_view,
            "article": {"source_id": note.id, "title": brief.title if brief and brief.title else note.title,
                        "chapter": self.chapter_of[note.id],
                        "summary": brief.summary if brief else "",
                        "connections": [{"id": i, "title": self.notes[i].title}
                                        for i in (brief.connections if brief else []) if i in self.notes and i != note.id]},
            "part": {"number": number, "total": len(parts)},
            "previous_context": parts[number - 2][-600:] if number > 1 else "",
            "source": part,
        }) for number, part in enumerate(parts, 1)]

    def run(self, task) -> WrittenPart:
        source_id, source, payload = task
        request, cache = self.request, self.cache
        best, best_missing, error = None, [], None
        for attempt in range(2):
            attempt_payload = {**payload, "missing": best_missing[:40]} if best_missing else payload
            try:
                part = WrittenPart.model_validate(cache.call("write", self.instructions, attempt_payload, self.schema))
            except ValidationError:
                cache.forget("write", self.instructions, attempt_payload, self.schema)
                continue
            except ValueError as exc:
                error = exc
                continue
            if request.writing_mode == "original":
                part.markdown = ""
            if request.study_aids == "none":
                part.aids = ""
            if request.writing_mode != "original" and not part.markdown.strip() or \
                    request.study_aids != "none" and not part.aids.strip():
                cache.forget("write", self.instructions, attempt_payload, self.schema)
                continue
            missing = missing_tokens(source, part.markdown) if self.check else []
            if best is None or len(missing) < len(best_missing):
                best, best_missing = part, missing
            if len(missing) < 3 or len(missing) <= len(required_tokens(source)) * 0.15:
                break
        if best is None:
            # Finished parts stay cached: a retry only redoes what is missing.
            raise ValueError(f"La IA no completó la redacción de «{self.notes[source_id].title}». "
                             "Reintenta la edición; las partes terminadas se reutilizarán.") from error
        return best


def concurrency():
    # Four parallel calls halved a 13-note edition without slowing each call.
    return max(1, int(os.getenv("AI_CONCURRENCY", "4")))


def chunk_limit():
    return int(os.getenv("AI_CHUNK_CHARS", "20000"))


class Status:
    """Progress of the parts written in parallel."""

    def __init__(self, progress, parts: int):
        self.progress, self.lock = progress, threading.Lock()
        self.parts, self.done = parts, 0

    def update(self, parts=0, more_parts=0):
        with self.lock:
            self.done += parts
            self.parts += more_parts
            self.progress(f"Redactando: {self.done} de {self.parts} partes listas.")


def plan_publication(request: PublicationRequest, cache_dir: Path | None = None, progress=lambda _: None) -> EditorialPlan:
    if not request.use_ai and request.artwork != "generated":
        return EditorialPlan(
            title=request.title.strip() or "Lecturas en Prelo",
            subtitle=DEFAULT_SUBTITLE[request.language],
            chapters=[Chapter(title=n.title, source_ids=[n.id]) for n in request.notes],
        )
    if not ai_available():
        raise ValueError("Activa un proveedor de IA en el servidor para usar esta opción.")
    cache = Cache(cache_dir)
    progress("Preparando el plan editorial del número.")
    outline = make_outline(request, cache)
    plan = EditorialPlan(**outline.model_dump(exclude={"briefs"}))
    if request.title.strip():
        plan.title = request.title.strip()
    if request.writing_mode != "original" or request.study_aids != "none":
        writer = Writer(request, outline, cache)
        order = [i for c in outline.chapters for i in c.source_ids]
        notes = {n.id: n for n in request.notes}
        tasks = {i: writer.tasks(notes[i]) for i in order}
        status = Status(progress, sum(map(len, tasks.values())))
        status.update()
        pool = ThreadPoolExecutor(max_workers=concurrency(), thread_name_prefix="margen-ai")
        try:
            written = {i: [pool.submit(writer.run, task) for task in tasks[i]] for i in order}
            for futures in written.values():
                for future in futures:
                    future.add_done_callback(lambda f: f.exception() or status.update(parts=1))
            articles = []
            for source_id in order:
                parts = [future.result() for future in written[source_id]]
                brief = writer.briefs.get(source_id)
                articles.append(EditedArticle(
                    source_id=source_id, title=brief.title.strip() if brief else "",
                    markdown="\n\n".join(p.markdown.strip() for p in parts if p.markdown.strip()),
                    aids="\n\n".join(p.aids.strip() for p in parts if p.aids.strip())))
        except BaseException:
            pool.shutdown(wait=True, cancel_futures=True)
            raise
        pool.shutdown(wait=True)
        plan.articles = articles
    # Validate the complete editorial result before rendering any edition.
    return plan.verify_visuals(request)
