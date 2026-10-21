"""Persisted job status and idempotent submission for multi-minute publications."""
import hashlib
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from .models import PublicationRequest

POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="margen-publication")
LOCK = threading.Lock()
ACTIVE = set()


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
        record = {"id": job_id, "state": "queued", "message": "Edición en cola.",
                  "created_at": now(), "updated_at": now(), "publication_id": None, "fingerprint": fingerprint}
        ACTIVE.add(key)
        write(path, record)

    def progress(message):
        with LOCK:
            record.update(state="running", message=message, updated_at=now())
            write(path, record)

    def run():
        try:
            result = build(request, job_id, progress)
            with LOCK:
                record.update(state="complete", message="Edición terminada.", publication_id=result["id"], updated_at=now())
                write(path, record)
        except Exception as exc:
            with LOCK:
                message = str(exc) if isinstance(exc, ValueError) else "No se ha podido completar la edición."
                record.update(state="failed", message=message, updated_at=now())
                write(path, record)
        finally:
            with LOCK:
                ACTIVE.discard(key)
    POOL.submit(run)
    return dict(record)
