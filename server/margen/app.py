import hmac
import json
import os
import shutil
import uuid
import zipfile
import io
import threading
import time
import httpx
from pathlib import Path
from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from . import __version__
from .models import PublicationRequest, HighlightsRequest, WritingMode, StudyAids, Language
from .editor import ai_available, plan_publication
from .epub import build_epub
from .highlights import resolve
from .artwork import generate_visuals
from . import jobs, kobo, library
from pydantic import BaseModel, Field
from typing import Annotated, Literal

BUILD_LOCK = threading.Lock()
BRIDGE_STATUS = {}


def data_root():
    root = Path(os.getenv("MARGEN_DATA", "./data"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def auth(authorization: str = Header(default="")):
    token = os.getenv("MARGEN_TOKEN", "")
    if len(token) < 24:
        raise HTTPException(503, "Configura MARGEN_TOKEN con al menos 24 caracteres.")
    if not hmac.compare_digest(authorization, "Bearer " + token):
        raise HTTPException(401, "Credencial de Prelo no válida.")


app = FastAPI(title="Prelo", version=__version__, docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    # Return the reason, never Pydantic's echoed input (which can contain full notes).
    messages = []
    for error in exc.errors()[:5]:
        location = ".".join(str(part) for part in error["loc"] if part != "body")
        message = error["msg"].removeprefix("Value error, ")
        messages.append(f"{location}: {message}" if location else message)
    return JSONResponse({"detail": "\n".join(messages)}, status_code=422)


@app.exception_handler(ValueError)
async def invalid_value(request, exc):
    return JSONResponse({"detail": str(exc)}, status_code=422)


@app.middleware("http")
async def limit_body(request: Request, call_next):
    # Check before Pydantic loads large base64 images, including chunked requests.
    if request.method in {"POST", "PUT"} and request.url.path != "/v1/kobo/uploads":
        size = 0
        chunks = []
        async for chunk in request.stream():
            size += len(chunk)
            if size > 36_000_000:
                return JSONResponse({"detail": "Publicación demasiado grande (máximo 36 MB)."}, 413)
            chunks.append(chunk)
        request._body = b"".join(chunks)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@app.get("/v1/status", dependencies=[Depends(auth)])
def status():
    configured = ai_available()
    ready, bridge_version = configured, None
    if configured and os.getenv("AI_PROVIDER") == "codex-bridge":
        url = os.environ["CODEX_BRIDGE_URL"].rstrip("/")
        cached = BRIDGE_STATUS.get(url)
        if not cached or time.monotonic() - cached[0] > 30:
            try:
                with httpx.Client(timeout=2, follow_redirects=False) as client:
                    response = client.get(url + "/health")
                    response.raise_for_status()
                    health = response.json()
            except Exception:
                health = {}
            cached = (time.monotonic(), health)
            BRIDGE_STATUS.clear()
            BRIDGE_STATUS[url] = cached
        ready = cached[1].get("status") == "ok" and cached[1].get("authenticated") is True
        bridge_version = cached[1].get("version")
    return {"ai_configured": configured, "ai_available": ready, "bridge_version": bridge_version,
            "protocol_version": 2, "model": os.getenv("AI_MODEL") or (
                "Codex · cuenta de ChatGPT" if os.getenv("AI_PROVIDER", "").startswith("codex") else ""),
            "image_generation_available": ready and os.getenv("AI_PROVIDER") in {"codex-bridge", "codex-cli"}}


def load_publication(edition_id):
    try:
        if str(uuid.UUID(edition_id)) != edition_id:
            raise ValueError()
    except ValueError:
        raise HTTPException(404, "Edición no encontrada.")
    path = data_root() / edition_id / "manifest.json"
    if not path.exists():
        raise HTTPException(404, "Edición no encontrada.")
    record = next((r for r in library.records(data_root()) if r["id"] == edition_id), None)
    if record is None:
        raise HTTPException(409, "La ficha de esta edición está dañada. Recupérala desde una copia.")
    return record


@app.get("/v1/publications", dependencies=[Depends(auth)])
def publications():
    return [{k: p.get(k) for k in ["id", "title", "subtitle", "filename", "created_at", "style", "ai_used", "warnings",
                                  "available", "pinned", "delivery", "bytes", "archived_at", "delivered_at"]}
            for p in library.records(data_root())]


@app.post("/v1/publications", dependencies=[Depends(auth)], status_code=201)
def publish(request: PublicationRequest):
    try:
        return build_publication(request, str(uuid.uuid4()))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


def build_publication(request, edition_id, progress=lambda _: None, cancelled=lambda: False):
    with BUILD_LOCK:
        return _build_publication(request, edition_id, progress, cancelled)


def _build_publication(request, edition_id, progress, cancelled):
    staging = data_root() / (".building-" + edition_id)
    try:
        with library.LOCK:
            if library.storage(data_root())["free_disk_bytes"] < 256_000_000:
                raise ValueError("Queda poco espacio libre en el disco del servicio. Libera espacio antes de generar.")
        progress("Organizando el contenido y preparando la dirección visual." if request.use_ai or request.artwork == "generated" else "Preparando el cuaderno de estudio.")
        plan = plan_publication(request, data_root() / ".ai-cache", progress, cancelled)
        illustrations = generate_visuals(request, plan, data_root() / ".art-cache", progress, cancelled)
        progress("Maquetando la portada, los artículos y el índice.")
        record = build_epub(request, plan, edition_id, staging, illustrations)
        (staging / "manifest.json").write_text(json.dumps(record, ensure_ascii=False, indent=2))
        if cancelled():
            raise jobs.Cancelled()
        with library.LOCK:
            library.cleanup(data_root(), protected=[edition_id])
            staging.rename(data_root() / edition_id)
            library.records(data_root())
            if request.send_to_kobo:
                library.change(data_root(), edition_id, "queue")
        return load_publication(edition_id)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


class JobSubmission(BaseModel):
    id: str
    publication: PublicationRequest


@app.post("/v1/jobs", dependencies=[Depends(auth)], status_code=202)
def submit_job(submission: JobSubmission):
    try:
        return jobs.submit(data_root(), submission.id, submission.publication, build_publication)
    except jobs.QueueFull as exc:
        raise HTTPException(429, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/v1/jobs/{job_id}/cancel", dependencies=[Depends(auth)])
def cancel_job(job_id: str):
    try:
        return {k: v for k, v in jobs.cancel(data_root(), job_id).items() if k != "fingerprint"}
    except FileNotFoundError:
        raise HTTPException(404, "Trabajo no encontrado.")
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.get("/v1/jobs/{job_id}", dependencies=[Depends(auth)])
def job_status(job_id: str):
    try:
        return jobs.read(data_root(), job_id)
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "Trabajo no encontrado.")


@app.get("/v1/jobs", dependencies=[Depends(auth)])
def all_jobs():
    paths = sorted((data_root() / ".jobs").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:100]
    return [{k: v for k, v in jobs.read(data_root(), p.stem).items() if k != "fingerprint"} for p in paths]


@app.get("/v1/publications/{edition_id}", dependencies=[Depends(auth)])
def publication(edition_id: str):
    return load_publication(edition_id)


@app.get("/v1/publications/{edition_id}/epub", dependencies=[Depends(auth)])
def download(edition_id: str):
    with library.LOCK:
        record = load_publication(edition_id)
        if not record["available"]:
            raise HTTPException(410, "El EPUB se retiró para liberar espacio. Su procedencia y subrayados se conservan.")
        return Response((data_root() / edition_id / record["filename"]).read_bytes(),
                        media_type="application/epub+zip",
                        headers={"Content-Disposition": f'attachment; filename="{record["filename"]}"'})


@app.get("/v1/publications/{edition_id}/cover", dependencies=[Depends(auth)])
def cover(edition_id: str):
    with library.LOCK:
        record = load_publication(edition_id)
        if not record["available"]:
            raise HTTPException(410, "Portada retirada.")
        return Response((data_root() / edition_id / "cover.svg").read_bytes(), media_type="image/svg+xml")


@app.get("/v1/publications/{edition_id}/artwork/{artwork_id}", dependencies=[Depends(auth)])
def artwork_image(edition_id: str, artwork_id: str):
    with library.LOCK:
        record = load_publication(edition_id)
        if not record["available"]:
            raise HTTPException(410, "Ilustraciones retiradas.")
        visual = next((v for v in record.get("artwork", []) if v["id"] == artwork_id and v["placement"] == "inside"), None)
        if not visual:
            raise HTTPException(404, "Ilustración no encontrada.")
        with zipfile.ZipFile(data_root() / edition_id / record["filename"]) as book:
            names = set(book.namelist())
            # Newer editions carry opening art only composed into its opener page.
            name = next(n for n in (f"EPUB/art/{artwork_id}.jpg", f"EPUB/art/o_{visual['source_ids'][0]}.jpg") if n in names)
            return Response(book.read(name), media_type="image/jpeg")


@app.post("/v1/highlights/resolve", dependencies=[Depends(auth)])
def resolve_highlights(request: HighlightsRequest):
    records = {r["id"]: r for r in library.records(data_root())}
    return {"highlights": [resolve(h, records) for h in request.highlights]}


class SourceIdentity(BaseModel):
    path: str = Field(min_length=1, max_length=1000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    id: str | None = None


class SourceRegistration(BaseModel):
    notes: list[SourceIdentity] = Field(min_length=1, max_length=100)


@app.post("/v1/sources", dependencies=[Depends(auth)])
def register_sources(payload: SourceRegistration):
    return {"notes": library.source_ids(data_root(), [n.model_dump() for n in payload.notes])}


@app.get("/v1/library", dependencies=[Depends(auth)])
def library_status():
    return {**library.dashboard(data_root()), "jobs": all_jobs(), "version": __version__}


class LibraryAction(BaseModel):
    action: Literal["queue", "cancel", "pin", "unpin", "delete"]


@app.post("/v1/publications/{edition_id}/action", dependencies=[Depends(auth)])
def library_action(edition_id: str, payload: LibraryAction):
    with library.LOCK:
        return library.change(data_root(), edition_id, payload.action)


class StorageSettings(BaseModel):
    limit_gb: float = Field(ge=1, le=1000)


def require_idle():
    if BUILD_LOCK.locked():
        raise HTTPException(409, "Espera a que termine la generación antes de limpiar o cambiar el límite.")
    with jobs.LOCK:
        if jobs.ACTIVE:
            raise HTTPException(409, "Espera a que termine la generación antes de limpiar o cambiar el límite.")


@app.post("/v1/storage/settings", dependencies=[Depends(auth)])
def storage_settings(payload: StorageSettings):
    return maintenance(lambda: library.set_limit(data_root(), payload.limit_gb))


@app.post("/v1/storage/cleanup", dependencies=[Depends(auth)])
def storage_cleanup():
    return maintenance(lambda: library.cleanup(data_root(), force=True))


def maintenance(action):
    require_idle()
    if not BUILD_LOCK.acquire(blocking=False):
        raise HTTPException(409, "Hay una generación en curso.")
    try:
        return action()
    finally:
        BUILD_LOCK.release()


@app.get("/v1/deliveries", dependencies=[Depends(auth)])
def pending_deliveries():
    return [r for r in publications() if r["delivery"] in {"queued", "transferring"} and r["available"]]


class Receipt(BaseModel):
    checksum: str = Field(pattern=r"^[a-f0-9]{64}$")
    device: str = Field(min_length=1, max_length=100)


class Claim(BaseModel):
    device: str = Field(min_length=1, max_length=100)


@app.post("/v1/deliveries/{edition_id}/claim", dependencies=[Depends(auth)])
def claim_delivery(edition_id: str, payload: Claim):
    library.claim(data_root(), edition_id, payload.device)
    return {"ok": True}


@app.post("/v1/deliveries/{edition_id}/receipt", dependencies=[Depends(auth)])
def delivery_receipt(edition_id: str, payload: Receipt):
    with library.LOCK:
        library.receipt(data_root(), edition_id, payload.checksum, payload.device)
    return {"ok": True}


class DeviceStatus(BaseModel):
    version: str = Field(default="", max_length=40)
    state: Literal["disconnected", "working", "ready", "error"]
    message: str = Field(max_length=500)
    device: str = Field(default="", max_length=100)
    last_sync: dict | None = None


class KoboBook(BaseModel):
    id: str = Field(max_length=500)
    path: str = Field(default="", max_length=500)
    edition: str = Field(default="", pattern=r"^([0-9a-f-]{36})?$")
    title: str = Field(default="", max_length=300)
    author: str = Field(default="", max_length=300)
    percent: int = Field(default=0, ge=0, le=100)
    last_read: str = Field(default="", max_length=40)
    status: str = Field(default="", max_length=10)
    present: bool = False
    sha256: str = Field(default="", pattern=r"^([a-f0-9]{64})?$")


class Inventory(BaseModel):
    device: str = Field(default="", max_length=100)
    books: list[KoboBook] = Field(default_factory=list, max_length=5000)
    unimported: list[Annotated[str, Field(pattern=r"^[0-9a-f-]{36}$")]] = Field(default_factory=list, max_length=5000)


@app.post("/v1/device/inventory", dependencies=[Depends(auth)])
def update_inventory(payload: Inventory):
    library.save_inventory(data_root(), payload.model_dump())
    return {"books": len(payload.books)}


@app.get("/v1/device", dependencies=[Depends(auth)])
def device():
    return library.device_state(data_root())


@app.post("/v1/device", dependencies=[Depends(auth)])
def update_device(payload: DeviceStatus):
    return library.device_state(data_root(), payload.model_dump())


@app.post("/v1/device/sync", dependencies=[Depends(auth)])
def sync_device():
    return library.request_sync(data_root())


def invalid(exc):
    return HTTPException(422, str(exc))


class Removal(BaseModel):
    device: str = Field(min_length=1, max_length=100)
    path: str = Field(min_length=1, max_length=400)


class CommandResult(BaseModel):
    device: str = Field(min_length=1, max_length=100)
    claim_token: str = Field(min_length=1, max_length=100)
    ok: bool
    message: str = Field(default="", max_length=500)


@app.get("/v1/kobo", dependencies=[Depends(auth)])
def kobo_overview():
    return kobo.overview(data_root())


@app.get("/v1/kobo/highlights", dependencies=[Depends(auth)])
def kobo_highlights(volume: str):
    return {"highlights": kobo.highlights(data_root(), volume)}


@app.post("/v1/kobo/removals", dependencies=[Depends(auth)])
def kobo_removal(payload: Removal):
    try:
        return kobo.request_removal(data_root(), payload.path, payload.device)
    except ValueError as exc:
        raise invalid(exc)


@app.post("/v1/kobo/uploads", dependencies=[Depends(auth)])
async def kobo_upload(request: Request, filename: str, device: str = ""):
    import tempfile
    kobo.destination(data_root(), device)
    if int(request.headers.get("content-length") or 0) > kobo.MAX_UPLOAD:
        raise HTTPException(413, "El EPUB supera los 200 MB.")
    # Bound each upload on disk; do not accumulate a 200 MB body in middleware/RAM.
    with tempfile.TemporaryDirectory(prefix=".uploading-", dir=data_root()) as folder:
        path = Path(folder) / "book.partial"
        size = 0
        with path.open("wb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > kobo.MAX_UPLOAD:
                    raise HTTPException(413, "El EPUB supera los 200 MB.")
                if shutil.disk_usage(folder).free < len(chunk) + 128_000_000:
                    raise HTTPException(507, "Falta espacio temporal para recibir el EPUB.")
                output.write(chunk)
        try:
            return kobo.upload(data_root(), filename, path, device)
        except ValueError as exc:
            raise invalid(exc)


@app.get("/v1/kobo/uploads/{command_id}", dependencies=[Depends(auth)])
def kobo_upload_file(command_id: str):
    try:
        return FileResponse(kobo.upload_file(data_root(), command_id), media_type="application/epub+zip")
    except (ValueError, FileNotFoundError):
        raise HTTPException(404, "Subida no encontrada.")


@app.get("/v1/kobo/commands", dependencies=[Depends(auth)])
def kobo_pending(device: str = ""):
    return kobo.pending(data_root(), device)


@app.post("/v1/kobo/commands/{command_id}/claim", dependencies=[Depends(auth)])
def kobo_claim(command_id: str, payload: Claim):
    try:
        return kobo.claim(data_root(), command_id, payload.device)
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.delete("/v1/kobo/commands/{command_id}", dependencies=[Depends(auth)])
def kobo_cancel(command_id: str):
    try:
        kobo.cancel(data_root(), command_id)
        return {"cancelled": command_id}
    except ValueError as exc:
        raise invalid(exc)


@app.post("/v1/kobo/commands/{command_id}/done", dependencies=[Depends(auth)])
def kobo_done(command_id: str, payload: CommandResult):
    try:
        kobo.complete(data_root(), command_id, payload.ok, payload.message, payload.device, payload.claim_token)
        return {"done": command_id}
    except ValueError as exc:
        raise invalid(exc)


@app.post("/v1/annotations", dependencies=[Depends(auth)])
def retain_annotations(payload: HighlightsRequest):
    library.save_annotations(data_root(), [h.model_dump() for h in payload.highlights])
    return resolve_highlights(payload)


class Draft(BaseModel):
    id: str
    title: str = Field(default="", max_length=160)
    intent: str = Field(default="", max_length=2000)
    preserve_order: bool = False
    style: Literal["study", "retro90"] = "study"
    writing_mode: WritingMode = "original"
    study_aids: StudyAids = "none"
    language: Language | None = None
    use_ai: bool = False
    send_to_kobo: bool = True
    paths: list[str] = Field(min_length=1, max_length=100)


@app.get("/v1/drafts", dependencies=[Depends(auth)])
def list_drafts():
    return library.drafts(data_root())


@app.post("/v1/drafts", dependencies=[Depends(auth)])
def save_draft(payload: Draft):
    return library.drafts(data_root(), payload.id, payload.model_dump(exclude={"id"}))


@app.delete("/v1/drafts/{draft_id}", dependencies=[Depends(auth)])
def delete_draft(draft_id: str):
    return library.drafts(data_root(), draft_id)


@app.get("/v1/backup", dependencies=[Depends(auth)])
def export_backup():
    from starlette.background import BackgroundTask
    path = library.backup(data_root())
    return FileResponse(path, media_type="application/zip", filename="margen-backup.zip",
                        background=BackgroundTask(path.unlink, missing_ok=True))


@app.get("/v1/installation/package", dependencies=[Depends(auth)])
def installation_package():
    directory = data_root() / ".plugin-release"
    if not (directory / "main.js").is_file():
        raise HTTPException(503, "Paquete del plugin pendiente de instalar en el servidor.")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ("main.js", "manifest.json", "styles.css"):
            archive.write(directory / name, "margen/" + name)
        # Older installed bundles still use an external WASM file.
        if (directory / "sql-wasm.wasm").is_file():
            archive.write(directory / "sql-wasm.wasm", "margen/sql-wasm.wasm")
        archive.writestr("conexion-prelo.json", json.dumps({
            "serverUrl": os.environ.get("MARGEN_PUBLIC_URL", "http://127.0.0.1:8765"),
            "token": os.environ["MARGEN_TOKEN"],
            "outputFolder": os.environ.get("MARGEN_OUTPUT_FOLDER", "Prelo/Publicaciones"),
            "highlightsFolder": os.environ.get("MARGEN_HIGHLIGHTS_FOLDER", "Prelo/Subrayados"),
        }))
        archive.writestr("LEEME.txt", "Copia la carpeta margen en TU_VAULT/.obsidian/plugins/.\n"
                          "Activa Prelo y ejecuta «Prelo: Conectar con el servidor» para importar conexion-prelo.json.\n"
                          "El archivo de conexión es privado. No lo publiques ni lo guardes dentro del vault.\n"
                          "Al actualizar, sustituye solo main.js, manifest.json, styles.css y sql-wasm.wasm; conserva data.json.\n")
    return Response(stream.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": 'attachment; filename="prelo-obsidian.zip"'})
