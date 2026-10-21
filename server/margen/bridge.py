"""Loopback-only bridge: Docker -> host Codex CLI, credentials stay on the host."""
from fastapi import FastAPI, Depends, HTTPException
from .app import auth, limit_body
from .models import PublicationRequest
from .editor import outline_schema, INSTRUCTIONS
from .codex_editor import codex_plan
from .artwork import ArtworkRequest, codex_artwork

app = FastAPI(title="Prelo · Codex local", docs_url=None, redoc_url=None, openapi_url=None)
app.middleware("http")(limit_body)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/plan", dependencies=[Depends(auth)])
def plan(request: PublicationRequest):
    try:
        return codex_plan(request, outline_schema(), INSTRUCTIONS)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/v1/artwork", dependencies=[Depends(auth)])
def artwork(request: ArtworkRequest):
    try:
        return codex_artwork(request)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
