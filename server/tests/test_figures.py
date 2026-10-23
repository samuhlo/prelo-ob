"""Old images are reinterpreted only when the reading is confident; originals stay available."""
import base64
import io
import zipfile

import pytest
from lxml import etree
from PIL import Image

from margen import editor
from margen.diagrams import render_diagram
from margen.epub import build_epub
from margen.figures import apply_figures, decide
from margen.models import Diagram, ImageReading, PublicationRequest
from margen.editor import plan_publication

EDITION = "12345678-1234-1234-1234-123456789abc"


def png(color):
    stream = io.BytesIO()
    Image.new("RGB", (40, 20), color).save(stream, format="PNG")
    return base64.b64encode(stream.getvalue()).decode()


NAT = {"layout": "flow_down",
       "nodes": [{"id": "pc", "label": "Equipo 10.0.0.2", "kind": "device"},
                 {"id": "r", "label": "Router NAT", "kind": "device"},
                 {"id": "net", "label": "Internet", "kind": "network"}],
       "edges": [{"source": "pc", "target": "r", "label": "10.0.0.2", "style": "arrow"},
                 {"source": "r", "target": "net", "label": "198.64.41.1", "style": "arrow"}]}
EMPTY = {"layout": "flow_down", "nodes": [], "edges": []}


def reading(asset, kind, confidence="high", diagram=EMPTY, table=""):
    return {"asset_id": asset, "kind": kind, "description": f"Descripción de {asset}", "caption": f"Pie de {asset}",
            "confidence": confidence, "table_markdown": table, "diagram": diagram}


@pytest.mark.parametrize("layout", ["flow_down", "flow_right", "layers", "sequence"])
def test_every_layout_renders_well_formed_svg_with_its_labels(layout):
    svg = render_diagram(Diagram.model_validate({**NAT, "layout": layout}))
    tree = etree.fromstring(svg.encode())
    assert tree.tag == "{http://www.w3.org/2000/svg}svg"
    assert "Router NAT" in "".join(tree.itertext())
    assert tree.xpath("count(//*[local-name()='marker'])") == 0


def test_unusable_diagrams_are_not_drawn():
    assert render_diagram(Diagram.model_validate(EMPTY)) is None
    duplicate = {**NAT, "nodes": NAT["nodes"] + [NAT["nodes"][0]]}
    assert render_diagram(Diagram.model_validate(duplicate)) is None
    assert render_diagram(Diagram.model_validate({**NAT, "layout": "sequence", "edges": []})) is None


def test_only_confident_readings_replace_the_original():
    assert decide(ImageReading.model_validate(reading("a", "diagram", diagram=NAT)), "study").action == "diagram"
    assert decide(ImageReading.model_validate(reading("a", "diagram", "low", NAT)), "study").action == "caption"
    assert decide(ImageReading.model_validate(reading("a", "diagram", diagram=EMPTY)), "study").action == "caption"
    assert decide(ImageReading.model_validate(reading("a", "table", table="| A |\n|---|\n| 1 |")), "study").action == "table"
    assert decide(ImageReading.model_validate(reading("a", "decorative")), "study").action == "remove"
    assert decide(ImageReading.model_validate(reading("a", "decorative", "medium")), "study").action == "caption"


def test_figures_replace_references_and_link_the_original():
    figures = [decide(ImageReading.model_validate(r), "study") for r in
               [reading("d", "diagram", diagram=NAT), reading("t", "table", table="| A |\n|---|\n| 1 |"), reading("p", "photo")]]
    text = apply_figures("Uno\n\n![x](margen-asset:d)\n\nDos ![y](margen-asset:t)\n\n![z](margen-asset:p)\n\n![w](margen-asset:other)", figures, "gl")
    assert "![Descripción de d](margen-figure:d)\n\n*Pie de d*  \n[Ver a imaxe orixinal](margen-original:d)" in text
    assert "| A |" in text and "margen-asset:t" not in text
    assert "![Descripción de p](margen-asset:p)\n\n*Pie de p*" in text
    assert "![w](margen-asset:other)" in text


def test_redraw_reads_images_in_batches_and_builds_a_checkable_epub(monkeypatch, tmp_path):
    assets = [{"id": f"img{i}", "media_type": "image/png", "data": png(c)} for i, c in enumerate(["red", "blue", "green"])]
    markdown = "Topoloxía:\n\n![Esquema o captura](margen-asset:img0)\n\nTáboa:\n\n![Esquema o captura](margen-asset:img1)\n\n![x](margen-asset:img2)"
    request = PublicationRequest(notes=[{"id": "a", "title": "NAT", "path": "a.md", "markdown": markdown}],
                                 assets=assets, images="redraw", language="es")
    assert request.use_ai
    monkeypatch.setattr(editor, "ai_available", lambda: True)
    calls = []
    def complete(stage, instructions, payload, schema, images=None):
        calls.append((stage, payload, images))
        if stage == "vision":
            assert [i["asset_id"] for i in payload["images"]] == ["img0", "img1", "img2"]
            assert payload["images"][0]["text_after"].startswith("Táboa") and len(images) == 3
            assert all(base64.b64decode(i["data"]).startswith(b"\x89PNG") for i in images)
            return {"images": [reading("img0", "diagram", diagram=NAT),
                               reading("img1", "table", table="| Puerto | Uso |\n|---|---|\n| 22 | SSH |")]}
        # The plan runs alongside image reading, so it sees the original references.
        assert "margen-asset:img0" in payload["notes"][0]["markdown"]
        return {"title": "Redes", "subtitle": "", "visuals": [], "briefs": [],
                "chapters": [{"title": "NAT", "source_ids": ["a"]}]}
    monkeypatch.setattr(editor, "complete", complete)
    plan = plan_publication(request)
    assert sorted(c[0] for c in calls) == ["plan", "vision"]
    assert {f.asset_id: f.action for f in plan.figures} == {"img0": "diagram", "img1": "table"}
    record = build_epub(request, plan, EDITION, tmp_path)
    with zipfile.ZipFile(tmp_path / record["filename"]) as book:
        names = set(book.namelist())
        article = book.read("EPUB/text/n_a.xhtml").decode()
        assert "EPUB/figures/img0.svg" in names and 'src="../figures/img0.svg"' in article
        assert "<table>" in article and "SSH" in article
        assert 'href="originales.xhtml#o_img0"' in article and 'class="figure-caption"' in article
        assert 'src="../assets/img2.png"' in article
        appendix = book.read("EPUB/text/originales.xhtml").decode()
        assert 'id="o_img0"' in appendix and 'id="o_img1"' in appendix and "img2" not in appendix
        assert "originales.xhtml" in book.read("EPUB/text/nav.xhtml").decode()
        for name in names:
            if name.endswith((".xhtml", ".svg", ".opf")):
                etree.fromstring(book.read(name))


def test_bridge_and_codex_attach_images(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from margen.bridge import app
    import margen.codex_editor as codex
    token = "x" * 40
    monkeypatch.setenv("MARGEN_TOKEN", token)
    seen = {}
    def run(args, **kwargs):
        if args[1:3] == ["login", "status"]:
            return type("R", (), {"returncode": 0, "stdout": "Logged in using ChatGPT", "stderr": ""})()
        seen["args"] = args
        answer = args[args.index("--output-last-message") + 1]
        open(answer, "w").write('{"images": []}')
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    monkeypatch.setattr(codex.subprocess, "run", run)
    monkeypatch.setenv("CODEX_BIN", "/usr/bin/true")
    body = {"instructions": "x", "input": {}, "output_schema": {}, "model": "gpt-6.1-sol", "effort": "low",
            "images": [{"media_type": "image/png", "data": png("red")}]}
    response = TestClient(app).post("/v1/complete", headers={"Authorization": "Bearer " + token}, json=body)
    assert response.json() == {"images": []}
    images = [a for a in seen["args"] if a.startswith("--image=")]
    assert len(images) == 1 and images[0].endswith("image-01.png") and seen["args"][-1] == "-"
    assert seen["args"][seen["args"].index("--model") + 1] == "gpt-6.1-sol"
    too_many = {**body, "images": body["images"] * 9}
    assert TestClient(app).post("/v1/complete", headers={"Authorization": "Bearer " + token}, json=too_many).status_code == 422


def test_provider_failure_while_reading_images_is_reported(monkeypatch):
    request = PublicationRequest(notes=[{"id": "a", "title": "NAT", "path": "a.md", "markdown": "![x](margen-asset:img0)"}],
                                 assets=[{"id": "img0", "media_type": "image/png", "data": png("red")}], images="redraw")
    monkeypatch.setattr(editor, "ai_available", lambda: True)
    def complete(stage, instructions, payload, schema, images=None):
        raise ValueError("El modelo «x» no está disponible en tu cuenta de Codex.")
    monkeypatch.setattr(editor, "complete", complete)
    with pytest.raises(ValueError, match="no está disponible"):
        plan_publication(request)


@pytest.mark.parametrize("layout", ["flow_down", "sequence"])
def test_edge_labels_with_data_are_never_cut(layout):
    label = "4. Respuesta traducida: origen 8.8.8.8; destino 192.168.1.1"
    assert len(label) <= 60
    diagram = {"layout": layout, "nodes": NAT["nodes"][:3],
               "edges": [{"source": "pc", "target": "r", "label": label, "style": "arrow"}]}
    text = " ".join("".join(etree.fromstring(render_diagram(Diagram.model_validate(diagram)).encode()).itertext()).split())
    assert "…" not in text and "192.168.1.1" in text and "8.8.8.8" in text


def test_each_note_is_written_while_other_images_are_still_read(monkeypatch):
    import threading
    notes = [{"id": n, "title": n.upper(), "path": f"{n}.md", "markdown": f"Texto {n}.\n\n![x](margen-asset:{n}img)"}
             for n in ("a", "b")]
    request = PublicationRequest(notes=notes, assets=[{"id": f"{n}img", "media_type": "image/png", "data": png("red")}
                                                      for n in ("a", "b")], images="redraw", writing_mode="simple")
    monkeypatch.setattr(editor, "ai_available", lambda: True)
    monkeypatch.setenv("AI_CONCURRENCY", "3")
    a_written = threading.Event()
    def complete(stage, instructions, payload, schema, images=None):
        if stage == "plan":
            return {"title": "T", "subtitle": "", "visuals": [], "briefs": [],
                    "chapters": [{"title": "C", "source_ids": ["a", "b"]}]}
        if stage == "vision":
            asset = payload["images"][0]["asset_id"]
            if asset == "bimg":
                # Note b's images finish only after note a has started writing.
                assert a_written.wait(5), "note a waited for every image of the edition"
            table = "| Dato | Valor |\n|---|---|\n| " + asset + " | 1 |"
            return {"images": [reading(asset, "table", table=table)]}
        if payload["article"]["source_id"] == "a":
            assert "| aimg | 1 |" in payload["source"]
            a_written.set()
        return {"markdown": "Explicación. " + payload["source"], "aids": ""}
    monkeypatch.setattr(editor, "complete", complete)
    messages = []
    plan = plan_publication(request, progress=messages.append)
    assert [a.source_id for a in plan.articles] == ["a", "b"]
    assert "| bimg | 1 |" in plan.articles[1].markdown
    assert any("Leyendo imágenes: 2 de 2" in m for m in messages)
    assert any("redactando: 2 de 2 partes" in m for m in messages)
