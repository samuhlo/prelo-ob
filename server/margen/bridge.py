"""Loopback-only bridge: Docker -> host Codex CLI, credentials stay on the host."""
from typing import Literal
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field
from .app import auth, limit_body
from .codex_editor import codex_complete
from .editor import timeout
from .artwork import ArtworkRequest, codex_artwork

app = FastAPI(title="Prelo · Codex local", docs_url=None, redoc_url=None, openapi_url=None)
app.middleware("http")(limit_body)


class Completion(BaseModel):
    instructions: str = Field(min_length=1, max_length=60_000)
    input: dict
    output_schema: dict
    # Both reach Codex as arguments: keep them to plain identifiers.
    model: str = Field(default="", max_length=80, pattern=r"^([A-Za-z0-9][A-Za-z0-9._:-]*)?$")
    effort: Literal["", "minimal", "low", "medium", "high", "xhigh"] = ""


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/v1/complete", dependencies=[Depends(auth)])
def complete(request: Completion):
    try:
        return codex_complete(request.instructions, request.input, request.output_schema,
                              request.model, request.effort, timeout())
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@app.post("/v1/artwork", dependencies=[Depends(auth)])
def artwork(request: ArtworkRequest):
    try:
        return codex_artwork(request)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
