"""Persisted job status and idempotent submission for multi-minute publications."""
import hashlib
import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from .models import PublicationRequest

POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="margen-publication")
LOCK = threading.Lock()
ACTIVE = set()
CANCELLED = set()


class QueueFull(ValueError):
    pass


class Cancelled(ValueError):
    def __init__(self):
        super().__init__("Has cancelado la edición.")


def now():
    return datetime.now(timezone.utc).isoformat()


def job_path(root: Path, job_id: str):
    if str(uuid.UUID(job_id)) != job_id:
        raise ValueError("Identificador de trabajo no válido.")
    folder = root / ".jobs"
    folder.mkdir(exist_ok=True, parents=True)
    return folder / (job_id + ".json")


def write(path, record):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False))
    temporary.replace(path)


def read(root, job_id):
    path = job_path(root, job_id)
    record = json.loads(path.read_text())
    key = (str(root.resolve()), job_id)
    with LOCK:
        if record["state"] in {"queued", "running"} and key not in ACTIVE:
            # A service restart must not silently repeat paid generation.
            publication = root / job_id / "manifest.json"
            record.update(state="complete" if publication.exists() else "failed", updated_at=now(),
                          message="Edición terminada." if publication.exists() else "El servicio se reinició. Vuelve a crear la edición para reintentarlo.",
                          publication_id=job_id if publication.exists() else None)
            write(path, record)
    return record


def submit(root, job_id, request: PublicationRequest, build):
    path = job_path(root, job_id)
    fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
    key = (str(root.resolve()), job_id)
    with LOCK:
        if path.exists():
            record = json.loads(path.read_text())
            if record["fingerprint"] != fingerprint:
                raise ValueError("El identificador ya corresponde a otra selección.")
            return record
        if sum(k[0] == key[0] for k in ACTIVE) >= max(1, int(os.getenv("MARGEN_MAX_JOBS", "4"))):
            raise QueueFull("La cola de ediciones está llena. Espera a que termine o cancela una edición.")
        record = {"id": job_id, "state": "queued", "message": "Edición en cola.",
                  "created_at": now(), "updated_at": now(), "publication_id": None, "fingerprint": fingerprint}
        write(path, record)
        ACTIVE.add(key)

    def cancelled():
        with LOCK:
            return key in CANCELLED

    def progress(message):
        if cancelled():
            raise Cancelled()
        with LOCK:
            record.update(state="running", message=message, updated_at=now())
            write(path, record)

    def run():
        try:
            if cancelled():
                raise Cancelled()
            result = build(request, job_id, progress, cancelled)
            with LOCK:
                record.update(state="complete", message="Edición terminada.", publication_id=result["id"], updated_at=now())
                write(path, record)
        except Exception as exc:
            with LOCK:
                message = str(exc) if isinstance(exc, ValueError) else "No se ha podido completar la edición."
                record.update(state="cancelled" if key in CANCELLED else "failed", message=message, updated_at=now())
                write(path, record)
        finally:
            with LOCK:
                ACTIVE.discard(key)
                CANCELLED.discard(key)
    try:
        POOL.submit(run)
    except BaseException:
        # Persistence succeeded, but no worker owns this job. read() will recover
        # its queued record as failed, including when the disk remains unwritable.
        with LOCK:
            ACTIVE.discard(key)
            CANCELLED.discard(key)
        raise
    return dict(record)


def cancel(root, job_id):
    """Stops a running edition at its next step; parts already being written finish first."""
    path = job_path(root, job_id)
    key = (str(root.resolve()), job_id)
    with LOCK:
        if key not in ACTIVE:
            raise ValueError("Esta edición ya no está en marcha.")
        CANCELLED.add(key)
        record = json.loads(path.read_text())
        record.update(message="Cancelando la edición…", updated_at=now())
        write(path, record)
    return record
