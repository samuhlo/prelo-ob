import base64
import re
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator


class Source(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    path: str = Field(min_length=1, max_length=1000)
    title: str = Field(min_length=1, max_length=200)
    markdown: str = Field(max_length=200_000)
    original_sha256: str = Field(default="", pattern=r"^([a-f0-9]{64})?$")


class Asset(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    media_type: Literal["image/png", "image/jpeg", "image/gif", "image/webp"]
    data: str = Field(max_length=12_000_000)

    @field_validator("data")
    @classmethod
    def valid_base64(cls, value):
        base64.b64decode(value, validate=True)
        return value

    @model_validator(mode="after")
    def valid_image(self):
        raw = base64.b64decode(self.data)
        signatures = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff",
                      "image/gif": b"GIF8", "image/webp": b"RIFF"}
        if not raw.startswith(signatures[self.media_type]):
            raise ValueError("El adjunto no coincide con el tipo de imagen.")
        if self.media_type == "image/webp" and raw[8:12] != b"WEBP":
            raise ValueError("WebP no válido.")
        return self


class PublicationRequest(BaseModel):
    title: str = Field(default="", max_length=160)
    intent: str = Field(default="", max_length=2000)
    style: Literal["editorial", "retro90", "study"] = "study"
    artwork: Literal["none", "generated"] = "none"
    use_ai: bool = False
    send_to_kobo: bool = False
    notes: list[Source] = Field(min_length=1, max_length=100)
    assets: list[Asset] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def unique_ids_and_size(self):
        if self.style == "editorial":
            self.style = "study"
        if self.style == "study" and self.artwork != "none":
            raise ValueError("Revista de estudio no genera ilustraciones.")
        for values in [self.notes, self.assets]:
            if len({v.id for v in values}) != len(values):
                raise ValueError("Identificadores repetidos.")
        if sum(len(n.markdown) for n in self.notes) > 600_000:
            raise ValueError("Selecciona menos notas: máximo 600.000 caracteres por edición.")
        if sum(len(a.data) for a in self.assets) > 32_000_000:
            raise ValueError("Los adjuntos superan el límite de 32 MB.")
        return self


class Chapter(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    source_ids: list[str] = Field(min_length=1)


class VisualBrief(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    placement: Literal["cover", "inside"]
    source_ids: list[str] = Field(min_length=1, max_length=100)
    concept: str = Field(min_length=1, max_length=400)
    description: str = Field(min_length=1, max_length=2000)
    caption: str = Field(max_length=500)
    anchor_heading: str = Field(default="", max_length=200)


class EditorialPlan(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    subtitle: str = Field(max_length=240)
    chapters: list[Chapter] = Field(min_length=1, max_length=100)
    visuals: list[VisualBrief] = Field(default_factory=list, max_length=3)

    def verify_sources(self, notes: list[Source]):
        ids = [i for c in self.chapters for i in c.source_ids]
        if len(ids) != len(set(ids)) or set(ids) != {n.id for n in notes}:
            raise ValueError("La propuesta debe incluir todas las notas exactamente una vez.")
        known = {n.id for n in notes}
        if len({v.id for v in self.visuals}) != len(self.visuals):
            raise ValueError("Identificadores de ilustración repetidos.")
        if any(not set(v.source_ids).issubset(known) for v in self.visuals):
            raise ValueError("Una ilustración referencia notas que no están en la selección.")
        return self

    def verify_visuals(self, request: PublicationRequest):
        self.verify_sources(request.notes)
        if request.style == "retro90" and request.artwork == "generated":
            if sum(v.placement == "cover" for v in self.visuals) != 1 or not any(v.placement == "inside" for v in self.visuals):
                raise ValueError("La revista necesita una portada temática y al menos una ilustración interior.")
        elif self.visuals:
            raise ValueError("Se propusieron ilustraciones para una edición sin generación visual.")
        return self


class Highlight(BaseModel):
    id: str = Field(min_length=1, max_length=300)
    volume_id: str = Field(max_length=2000)
    content_id: str = Field(default="", max_length=2000)
    start_path: str = Field(default="", max_length=2000)
    text: str = Field(default="", max_length=100_000)
    annotation: str = Field(default="", max_length=100_000)
    title: str = Field(default="", max_length=1000)
    author: str = Field(default="", max_length=1000)
    created_at: str = Field(default="", max_length=100)
    color: str = Field(default="", max_length=100)


class HighlightsRequest(BaseModel):
    highlights: list[Highlight] = Field(max_length=500)
