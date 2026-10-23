"""Editorial settings must reach the EPUB without changing original provenance."""
import hashlib
import json
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient
from lxml import etree

from margen.app import app
from margen.editor import plan_publication
from margen.epub import build_epub
from margen.highlights import resolve
from margen.models import EditorialPlan, Highlight, PublicationRequest

NOTES = [
    {"id": "a", "title": "Primero", "path": "Primero.md", "markdown": "Texto original A."},
    {"id": "b", "title": "Segundo", "path": "Segundo.md", "markdown": "Texto original B."},
]
EDITION = "12345678-1234-1234-1234-123456789abc"


def plan_for(mode, aids):
    return EditorialPlan(title="Lectura", subtitle="", chapters=[{"title": "Tema", "source_ids": ["a", "b"]}],
        articles=[{"source_id": n["id"],
                   "markdown": f"Explicación {n['id']}. [Otra nota](margen-note:b)" if mode != "original" else "",
                   "aids": "## Esquema\n\n- Idea\n  - Detalle\n\n| Concepto | Explicación |\n|---|---|\n| A | B |" if aids != "none" else ""}
                  for n in NOTES] if mode != "original" or aids != "none" else [])


@pytest.mark.parametrize("mode", ["original", "narrative", "simple", "step_by_step", "review"])
@pytest.mark.parametrize("aids", ["none", "visual", "practice", "complete"])
def test_modes_render_complete_valid_epubs_and_keep_provenance(tmp_path, mode, aids):
    request = PublicationRequest(notes=NOTES, writing_mode=mode, study_aids=aids)
    record = build_epub(request, plan_for(mode, aids), EDITION, tmp_path)
    assert request.use_ai == (mode != "original" or aids != "none")
    assert record["writing_mode"] == mode and record["study_aids"] == aids
    assert request.notes[0].markdown == NOTES[0]["markdown"]
    assert record["sources"][0]["sha256"] == hashlib.sha256(NOTES[0]["markdown"].encode()).hexdigest()
    with zipfile.ZipFile(tmp_path / record["filename"]) as book:
        for name in book.namelist():
            if name.endswith((".xhtml", ".opf", ".xml", ".svg")):
                etree.fromstring(book.read(name))
        content = book.read("EPUB/text/n_a.xhtml").decode()
        assert ("Texto original A." in content) == (mode == "original")
        assert ("Texto adaptado con IA" in content) == (mode != "original")
        assert ("<table>" in content) == (aids != "none")
        tree = etree.fromstring(content.encode())
        ids = tree.xpath("//@id")
        assert len(ids) == len(set(ids))
        if mode != "original":
            # Both notes are short, so they share a file and link by anchor.
            assert 'href="n_a.xhtml#n_b"' in content
    quote = "Explicación a." if mode != "original" else "Texto original A."
    highlight = resolve(Highlight(id="one", volume_id=record["filename"], text=quote), {EDITION: record})
    assert highlight["source"]["path"] == "Primero.md"
    assert highlight["match"] == "exact_text"
    assert bool(highlight["content_note"]) == (mode != "original" or aids != "none")


@pytest.mark.parametrize("invalid", ["missing", "duplicate", "unknown", "empty_body", "empty_aids"])
def test_incomplete_adaptation_is_rejected(tmp_path, invalid):
    request = PublicationRequest(notes=NOTES, writing_mode="simple", study_aids="complete")
    plan = plan_for("simple", "complete")
    if invalid == "missing": plan.articles.pop()
    if invalid == "duplicate": plan.articles.append(plan.articles[0])
    if invalid == "unknown": plan.articles[0].source_id = "unknown"
    if invalid == "empty_body": plan.articles[0].markdown = " "
    if invalid == "empty_aids": plan.articles[0].aids = " "
    with pytest.raises(ValueError):
        build_epub(request, plan, EDITION, tmp_path)
    assert not list(tmp_path.glob("*.epub"))


def test_original_cannot_be_silently_rewritten():
    request = PublicationRequest(notes=NOTES, study_aids="visual")
    with pytest.raises(ValueError, match="original"):
        plan_for("simple", "visual").verify_visuals(request)


@pytest.mark.parametrize("provider", ["http", "codex-cli", "codex-bridge"])
def test_settings_reach_every_provider(monkeypatch, provider):
    request = PublicationRequest(notes=NOTES, writing_mode="narrative", study_aids="complete", language="gl",
                                 intent="Cada tema seguido de su examen resuelto.", preserve_order=True)
    monkeypatch.setattr("margen.editor.ai_available", lambda: True)
    monkeypatch.setenv("AI_PROVIDER", provider)
    monkeypatch.setenv("AI_BASE_URL", "http://fixture/v1")
    monkeypatch.setenv("CODEX_BRIDGE_URL", "http://fixture")
    monkeypatch.setenv("MARGEN_TOKEN", "fixture")
    monkeypatch.setenv("AI_MODEL", "fixture")
    monkeypatch.setenv("AI_MODEL_PLAN", "planner")
    monkeypatch.setenv("AI_EFFORT_PLAN", "high")
    calls = []
    def answer(instructions, payload, model, effort):
        stage = "plan" if "notes" in payload else "write"
        calls.append((stage, model, effort))
        if stage == "plan":
            assert payload["intent"] == request.intent and payload["preserve_order"] is True
            assert payload["language"] == "gl" and "galego" in instructions
            assert [n["id"] for n in payload["notes"]] == ["a", "b"]
            return {"title": "Lectura", "subtitle": "", "chapters": [{"title": "Tema", "source_ids": ["a", "b"]}],
                    "visuals": [], "briefs": [{"source_id": "a", "summary": "Resumen A", "connections": ["b"]}]}
        assert payload["settings"]["writing_mode"] == "narrative" and payload["settings"]["study_aids"] == "complete"
        assert "revista narrativa" in instructions and "Preguntas" in instructions
        return {"markdown": f"Explicación de {payload['source'][-2]}.", "aids": "### Preguntas\n\n1. ¿Qué?"}
    def codex(instructions, payload, schema, model, effort, timeout, images):
        assert "markdown" in schema["required"] or "chapters" in schema["required"]
        return answer(instructions, payload, model, effort)
    def post(self, url, **kwargs):
        body = kwargs["json"]
        if provider == "http":
            result = answer(body["messages"][0]["content"], json.loads(body["messages"][1]["content"]),
                            body["model"], body.get("reasoning_effort", ""))
            result = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]}
        else:
            assert url == "http://fixture/v1/complete"
            result = answer(body["instructions"], body["input"], body["model"], body["effort"])
        return httpx.Response(200, request=httpx.Request("POST", url), json=result)
    monkeypatch.setattr("margen.codex_editor.codex_complete", codex)
    monkeypatch.setattr(httpx.Client, "post", post)
    plan = plan_publication(request)
    assert [a.markdown for a in plan.articles] == ["Explicación de A.", "Explicación de B."]
    assert calls[0] == ("plan", "planner", "high")
    assert sorted(calls[1:]) == [("write", "fixture", ""), ("write", "fixture", "")]


def test_drafts_round_trip_editorial_settings_and_old_defaults(tmp_path, monkeypatch):
    token = "x" * 40
    monkeypatch.setenv("MARGEN_DATA", str(tmp_path))
    monkeypatch.setenv("MARGEN_TOKEN", token)
    client = TestClient(app)
    headers = {"Authorization": "Bearer " + token}
    payload = {"id": EDITION, "paths": ["Primero.md"], "writing_mode": "simple",
               "study_aids": "complete", "use_ai": True, "send_to_kobo": False,
               "intent": "Tema y después examen.", "preserve_order": True}
    assert client.post("/v1/drafts", headers=headers, json=payload).status_code == 200
    draft = client.get("/v1/drafts", headers=headers).json()[0]
    for key, value in payload.items():
        assert draft[key] == value
    assert client.post("/v1/drafts", headers=headers, json={"id": EDITION, "paths": ["Primero.md"]}).status_code == 200
    draft = client.get("/v1/drafts", headers=headers).json()[0]
    assert draft["writing_mode"] == "original" and draft["study_aids"] == "none"


def test_rewriting_requires_provider_even_if_use_ai_was_false(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "disabled")
    with pytest.raises(ValueError, match="proveedor"):
        plan_publication(PublicationRequest(notes=NOTES, writing_mode="simple", use_ai=False))


@pytest.mark.parametrize("intent, expected_ai", [("Tema y después examen.", True), ("  ", False), ("", False)])
def test_extra_instructions_are_not_ignored_without_ai_toggle(monkeypatch, intent, expected_ai):
    request = PublicationRequest(notes=NOTES, intent=intent, use_ai=False)
    assert request.use_ai is expected_ai
    monkeypatch.setenv("AI_PROVIDER", "disabled")
    if expected_ai:
        with pytest.raises(ValueError, match="proveedor"):
            plan_publication(request)
    else:
        assert plan_publication(request).chapters[0].source_ids == ["a"]


def test_locked_order_rejects_reordering_and_keeps_epub_spine(tmp_path):
    request = PublicationRequest(notes=NOTES, preserve_order=True)
    plan = plan_for("original", "none")
    plan.chapters[0].source_ids.reverse()
    with pytest.raises(ValueError, match="orden"):
        build_epub(request, plan, EDITION, tmp_path)
    assert not list(tmp_path.glob("*.epub"))
    plan.chapters[0].source_ids.reverse()
    record = build_epub(request, plan, EDITION, tmp_path)
    with zipfile.ZipFile(tmp_path / record["filename"]) as book:
        package = etree.fromstring(book.read("EPUB/package.opf"))
        assert package.xpath("//*[local-name()='spine']/*/@idref") == ["cover", "nav", "n_a"]
        article = etree.fromstring(book.read("EPUB/text/n_a.xhtml"))
        assert article.xpath("//*[@class='article']/@id") == ["n_a", "n_b"]
    assert record["preserve_order"] is True


def test_long_notes_keep_their_own_file_and_short_ones_share(tmp_path):
    long_text = "Párrafo extenso sobre subredes. " * 80
    notes = [{"id": "a", "title": "Largo", "path": "Largo.md", "markdown": long_text},
             {"id": "b", "title": "Breve uno", "path": "B.md", "markdown": "Idea breve B."},
             {"id": "c", "title": "Breve dos", "path": "C.md", "markdown": "Idea breve C."},
             {"id": "d", "title": "Con imagen", "path": "D.md", "markdown": "![Esquema](margen-asset:missing)"}]
    request = PublicationRequest(notes=notes)
    plan = EditorialPlan(title="Lectura", subtitle="", chapters=[{"title": "Uno", "source_ids": ["a", "b"]},
                                                                 {"title": "Dos", "source_ids": ["c", "d"]}])
    record = build_epub(request, plan, EDITION, tmp_path)
    assert [s["href"] for s in record["sources"]] == ["text/n_a.xhtml", "text/n_b.xhtml", "text/n_b.xhtml", "text/n_d.xhtml"]
    with zipfile.ZipFile(tmp_path / record["filename"]) as book:
        package = etree.fromstring(book.read("EPUB/package.opf"))
        assert package.xpath("//*[local-name()='spine']/*/@idref") == ["cover", "nav", "n_a", "n_b", "n_d"]
        nav = book.read("EPUB/text/nav.xhtml").decode()
        assert 'href="n_b.xhtml#n_c"' in nav and "Fuente:" not in book.read("EPUB/text/n_a.xhtml").decode()
    shared = volume = record["filename"]
    location = f"file:///mnt/onboard/{volume}#(3)EPUB/text/n_b.xhtml"
    for quote, expected in [("Idea breve C.", "c"), ("Idea breve B.", "b")]:
        highlight = resolve(Highlight(id=quote, volume_id=shared, content_id=location, text=quote), {EDITION: record})
        assert highlight["source"]["id"] == expected and highlight["match"] == "exact_text"
    repeated = record | {"sources": [*record["sources"], {**record["sources"][2], "id": "e", "href": "text/n_x.xhtml"}]}
    within = resolve(Highlight(id="r", volume_id=shared, content_id=location, text="Idea breve C."), {EDITION: repeated})
    assert within["source"]["id"] == "c"
    single = resolve(Highlight(id="x", volume_id=shared, content_id=location.replace("n_b", "n_a"), text=""), {EDITION: record})
    assert single["source"]["id"] == "a" and single["match"] == "chapter"


def test_galician_edition_sets_language_and_labels(tmp_path):
    request = PublicationRequest(notes=NOTES, language="gl", writing_mode="simple", study_aids="visual")
    record = build_epub(request, plan_for("simple", "visual"), EDITION, tmp_path)
    assert record["language"] == "gl"
    with zipfile.ZipFile(tmp_path / record["filename"]) as book:
        package = etree.fromstring(book.read("EPUB/package.opf"))
        assert package.xpath("//*[local-name()='language']/text()") == ["gl"]
        content = book.read("EPUB/text/n_a.xhtml").decode()
        assert 'xml:lang="gl"' in content and "Apoios de estudo" in content and "nota orixinal" in content
        assert "NESTE CADERNO" in book.read("EPUB/cover.svg").decode()
    assert PublicationRequest(notes=NOTES).language == "es"
