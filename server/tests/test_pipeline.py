import base64
import copy
import io
import json
import uuid
import time
import zipfile
from pathlib import PurePosixPath
import httpx
import pytest
from fastapi.testclient import TestClient
from lxml import etree
from margen.app import app
from margen.editor import plan_publication
from margen.models import PublicationRequest, EditorialPlan

TOKEN = "test-token-" + "x" * 32
AUTH = {"Authorization": "Bearer " + TOKEN}
PAYLOAD = {
    "title": "Docker & lectura", "use_ai": False,
    "notes": [
        {"id": "a", "title": "Imágenes", "path": "clases/Imágenes.md",
         "markdown": "---\ntags: []\n---\n# Imágenes\n\nUna imagen es una plantilla.\n\n[Redes](margen-note:b)\n\n```sh\n[[literal]]\n```\n\n| A | B |\n|---|---|\n| 1 | 2 |"},
        {"id": "b", "title": "Redes", "path": "clases/Redes.md",
         "markdown": "# Redes\n\nlocalhost identifica al contenedor actual.\n\n[Manual](https://example.com?a=1&b=2)"},
    ],
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MARGEN_DATA", str(tmp_path))
    monkeypatch.setenv("MARGEN_TOKEN", TOKEN)
    return TestClient(app)


def publish(client, payload=None):
    response = client.post("/v1/publications", headers=AUTH, json=payload or PAYLOAD)
    assert response.status_code == 201, response.text
    return response.json()


def test_auth_and_health(client):
    assert client.get("/health").status_code == 200
    assert client.get("/v1/publications").status_code == 401
    assert client.post("/v1/publications", json=PAYLOAD).status_code == 401
    assert client.get("/v1/publications/not-a-uuid", headers=AUTH).status_code == 404


def test_cover_is_private_and_well_formed(client):
    record = publish(client)
    endpoint = f"/v1/publications/{record['id']}/cover"
    assert client.get(endpoint).status_code == 401
    response = client.get(endpoint, headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
    tree = etree.fromstring(response.content)
    assert tree.tag == "{http://www.w3.org/2000/svg}svg"
    assert tree.xpath("count(//*[local-name()='script'])") == 0
    assert record["title"] in "".join(tree.itertext())

def test_epub_can_be_traversed_and_sources_survive(client):
    record = publish(client)
    response = client.get(f"/v1/publications/{record['id']}/epub", headers=AUTH)
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as book:
        assert book.infolist()[0].filename == "mimetype"
        assert book.infolist()[0].compress_type == zipfile.ZIP_STORED
        assert book.read("mimetype") == b"application/epub+zip"
        names = set(book.namelist())
        for name in names:
            if name.endswith((".xhtml", ".xml", ".opf", ".svg")):
                root = etree.fromstring(book.read(name))
                if name.endswith(".xhtml"):
                    for href in root.xpath("//@href | //@src"):
                        if href.startswith("http"): continue
                        path = PurePosixPath(name).parent / href.split("#")[0]
                        parts = []
                        for p in path.parts:
                            if p == "..": parts.pop()
                            else: parts.append(p)
                        assert "/".join(parts) in names, href
        text = book.read("EPUB/text/n_a.xhtml").decode()
        assert "Una imagen es una plantilla." in text
        assert "tags: []" not in text
        assert "[[literal]]" in text  # code must never be rewritten as a wiki reference
        assert "<table" in text
    assert record["sources"][0]["path"] == "clases/Imágenes.md"
    second = publish(client)
    assert second["id"] != record["id"]
    assert len(client.get("/v1/publications", headers=AUTH).json()) == 2


def test_highlights_match_chapter_and_keep_ambiguity(client):
    record = publish(client)
    volume = f"file:///mnt/onboard/{record['filename']}"
    rows = [
        {"id": "one", "volume_id": volume, "content_id": volume + "!EPUB/text/n_a.xhtml", "text": "Una imagen"},
        {"id": "two", "volume_id": volume, "text": "localhost identifica al contenedor actual."},
        {"id": "three", "volume_id": volume, "text": "Texto que ya no está"},
        {"id": "four", "volume_id": "file:///mnt/onboard/novela.epub", "text": "Una cita", "title": "Novela", "author": "Autora"},
    ]
    result = client.post("/v1/highlights/resolve", headers=AUTH, json={"highlights": rows}).json()["highlights"]
    assert result[0]["source"]["id"] == "a"
    assert result[1]["source"]["id"] == "b"
    assert result[2]["match"] == "unresolved" and result[2]["source"] is None
    assert result[3]["match"] == "book" and result[3]["author"] == "Autora"
    assert result == client.post("/v1/highlights/resolve", headers=AUTH, json={"highlights": rows}).json()["highlights"]


def test_invalid_ai_outline_cannot_lose_or_duplicate_notes():
    notes = PublicationRequest(**PAYLOAD).notes
    for ids in [["a"], ["a", "b", "b"], ["a", "bogus"]]:
        plan = EditorialPlan(title="X", subtitle="", chapters=[{"title": "X", "source_ids": ids}])
        with pytest.raises(ValueError): plan.verify_sources(notes)


def test_ai_integration_with_provider_fixture(monkeypatch):
    monkeypatch.setenv("AI_BASE_URL", "http://local-model/v1")
    monkeypatch.setenv("AI_MODEL", "configured-model")
    plan = {"title": "Otro", "subtitle": "Una lectura", "chapters": [{"title": "Docker", "source_ids": ["b", "a"]}]}
    def post(self, url, **kwargs):
        assert url == "http://local-model/v1/chat/completions"
        assert kwargs["json"]["response_format"]["json_schema"]["strict"]
        return httpx.Response(200, request=httpx.Request("POST", url), json={
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(plan)}}],
        })
    monkeypatch.setattr(httpx.Client, "post", post)
    result = plan_publication(PublicationRequest(**{**PAYLOAD, "use_ai": True}))
    assert result.title == PAYLOAD["title"]
    assert result.chapters[0].source_ids == ["b", "a"]


def test_ai_requested_without_configuration_is_explicit_failure(client, monkeypatch):
    monkeypatch.delenv("AI_BASE_URL", raising=False)
    monkeypatch.delenv("AI_MODEL", raising=False)
    response = client.post("/v1/publications", headers=AUTH, json={**PAYLOAD, "use_ai": True})
    assert response.status_code == 422
    assert client.get("/v1/publications", headers=AUTH).json() == []


def test_images_packaged_and_remote_images_reported(client):
    payload = copy.deepcopy(PAYLOAD)
    payload["assets"] = [{"id": "pixel", "media_type": "image/png", "data":
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII="}]
    payload["notes"][0]["markdown"] += "\n\n![Pixel](margen-asset:pixel)\n\n![Remote](https://example.com/pic.png)"
    record = publish(client, payload)
    assert any("imagen no incluida" in w for w in record["warnings"])
    with zipfile.ZipFile(io.BytesIO(client.get(f"/v1/publications/{record['id']}/epub", headers=AUTH).content)) as book:
        assert "EPUB/assets/pixel.png" in book.namelist()
        assert 'src="https://' not in book.read("EPUB/text/n_a.xhtml").decode()


def test_duplicate_sources_rejected(client):
    payload = copy.deepcopy(PAYLOAD)
    payload["notes"].append(payload["notes"][0])
    assert client.post("/v1/publications", headers=AUTH, json=payload).status_code == 422


def test_publication_job_is_idempotent(client):
    job_id = str(uuid.uuid4())
    payload = {"id": job_id, "publication": PAYLOAD}
    assert client.post("/v1/jobs", headers=AUTH, json=payload).status_code == 202
    assert client.post("/v1/jobs", headers=AUTH, json=payload).status_code == 202
    # Generous bound for a cold, busy machine; the loop exits as soon as the job ends.
    for _ in range(1000):
        record = client.get(f"/v1/jobs/{job_id}", headers=AUTH).json()
        if record["state"] in {"complete", "failed"}: break
        time.sleep(.01)
    assert record["state"] == "complete", record
    assert record["publication_id"] == job_id
    assert len(client.get("/v1/publications", headers=AUTH).json()) == 1
    changed = {**payload, "publication": {**PAYLOAD, "title": "Otro contenido"}}
    assert client.post("/v1/jobs", headers=AUTH, json=changed).status_code == 422


def test_running_job_can_be_cancelled(client, monkeypatch):
    import threading
    import margen.app as service
    started = threading.Event()
    def slow_build(request, edition_id, progress, cancelled):
        started.set()
        while True:
            progress("Redactando…")
            time.sleep(.01)
    monkeypatch.setattr(service, "build_publication", slow_build)
    job_id = str(uuid.uuid4())
    assert client.post("/v1/jobs", headers=AUTH, json={"id": job_id, "publication": PAYLOAD}).status_code == 202
    assert started.wait(5)
    assert client.post(f"/v1/jobs/{job_id}/cancel", headers=AUTH).status_code == 200
    for _ in range(1000):
        record = client.get(f"/v1/jobs/{job_id}", headers=AUTH).json()
        if record["state"] == "cancelled": break
        time.sleep(.01)
    assert record["state"] == "cancelled" and "cancelado" in record["message"]
    assert client.post(f"/v1/jobs/{job_id}/cancel", headers=AUTH).status_code == 422
    assert not client.get("/v1/publications", headers=AUTH).json()

def retro_fixture():
    from PIL import Image
    stream = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(stream, format="JPEG")
    request = PublicationRequest(**{**PAYLOAD, "style": "retro90", "artwork": "generated"})
    plan = EditorialPlan(title="Docker", subtitle="Conceptos",
        chapters=[{"title": "Fundamentos", "source_ids": ["a", "b"]}],
        visuals=[
            {"id": "cover", "placement": "cover", "source_ids": ["a", "b"], "concept": "De la imagen al contenedor", "description": "Plantilla y varias instancias", "caption": ""},
            {"id": "networks", "placement": "inside", "source_ids": ["b"], "concept": "Redes", "description": "Conexiones entre contenedores.", "caption": "Redes entre contenedores."},
            {"id": "instances", "placement": "inside", "source_ids": ["a"], "concept": "Varias instancias", "description": "Una plantilla produce varias instancias.", "caption": "Una imagen permite crear varios contenedores."},
        ])
    return request, plan, base64.b64encode(stream.getvalue()).decode()


def test_content_specific_artwork_and_cache(client, tmp_path, monkeypatch):
    from margen.artwork import generate_visuals
    from margen.epub import build_epub
    import margen.artwork as art
    request, plan, data = retro_fixture()
    calls, running, peak = [], [0], [0]
    def fake(job):
        calls.append(job)
        running[0] += 1
        peak[0] = max(peak[0], running[0])
        # The cover is the slowest: results must still follow the plan's order.
        time.sleep(.15 if job.visual.id == "cover" else .05)
        running[0] -= 1
        return {"data": data, "media_type": "image/jpeg"}
    monkeypatch.setenv("AI_PROVIDER", "codex-cli")
    monkeypatch.setattr(art, "codex_artwork", fake)
    first = generate_visuals(request, plan, tmp_path / "cache")
    second = generate_visuals(request, plan, tmp_path / "cache")
    assert len(calls) == 3 and all(v["cache_hit"] for v in second)
    assert [v["id"] for v in first] == ["cover", "networks", "instances"] and peak[0] > 1
    assert next(c for c in calls if c.visual.id == "instances").sources[0].id == "a"
    assert "Una imagen es una plantilla" in first[2]["prompt"]
    edition = str(uuid.uuid4())
    folder = tmp_path / edition
    record = build_epub(request, plan, edition, folder, first)
    (folder / "manifest.json").write_text(json.dumps(record))
    with zipfile.ZipFile(folder / record["filename"]) as book:
        assert "data:image/jpeg;base64," in book.read("EPUB/cover.svg").decode()
        article = etree.fromstring(book.read("EPUB/text/n_a.xhtml"))
        # The opening art has its own composed page; the caption leads the text.
        assert article.xpath("count(//*[local-name()='div' and @class='illustration'])") == 0
        assert article.xpath("count(//*[local-name()='p' and @class='illustration-caption'])") == 1
        assert article.xpath("count(//*[local-name()='figcaption'])") == 0
        assert "Una imagen es una plantilla" in "".join(article.itertext())
        assert "EPUB/art/instances.jpg" in book.namelist()
        opener = etree.fromstring(book.read("EPUB/text/o_a.xhtml"))
        assert opener.xpath("//*[local-name()='image']/@*[local-name()='href']") == ["../art/instances.jpg"]
        assert "Imágenes" in "".join(opener.itertext())
        package = etree.fromstring(book.read("EPUB/package.opf"))
        assert package.xpath("//*[local-name()='spine']/*/@idref") == ["cover", "nav", "o_a", "n_a", "o_b", "n_b"]
        assert package.xpath("//*[@id='o_a']/@properties") == ["svg"]
    assert record["artwork"][2]["source_ids"] == ["a"]
    endpoint = f"/v1/publications/{edition}/artwork/instances"
    assert client.get(endpoint).status_code == 401
    image = client.get(endpoint, headers=AUTH)
    assert image.status_code == 200 and image.headers["content-type"] == "image/jpeg"
    assert image.content == base64.b64decode(data)
    assert client.get(f"/v1/publications/{edition}/artwork/missing", headers=AUTH).status_code == 404


def test_study_never_generates_images(tmp_path, monkeypatch):
    from margen.artwork import generate_visuals
    import margen.artwork as art
    monkeypatch.setattr(art, "codex_artwork", lambda *_: pytest.fail("Study should not generate artwork"))
    request = PublicationRequest(**PAYLOAD)
    plan = plan_publication(request)
    assert plan.visuals == [] and generate_visuals(request, plan, tmp_path) == []


def test_illustrations_must_reference_selected_sources():
    request, plan, _ = retro_fixture()
    plan.visuals[1].source_ids = ["missing"]
    with pytest.raises(ValueError): plan.verify_visuals(request)


def test_disabled_ai_stays_disabled_with_saved_provider_settings(monkeypatch):
    from margen.editor import ai_available
    monkeypatch.setenv('AI_PROVIDER', 'disabled')
    monkeypatch.setenv('AI_BASE_URL', 'https://provider.example.test/v1')
    monkeypatch.setenv('AI_MODEL', 'synthetic-model')
    assert ai_available() is False


@pytest.mark.parametrize("problem", ["missing_note", "shared_image", "duplicate_cover", "no_cover"])
def test_retro_requires_cover_and_an_asset_placed_in_every_note(problem):
    request, plan, _ = retro_fixture()
    if problem == "missing_note":
        plan.visuals.pop(1)
    elif problem == "shared_image":
        plan.visuals.pop(1)
        plan.visuals[1].source_ids = ["a", "b"]
    elif problem == "duplicate_cover":
        plan.visuals.append(plan.visuals[0].model_copy(update={"id": "cover2"}))
    else:
        plan.visuals.pop(0)
    with pytest.raises(ValueError):
        plan.verify_visuals(request)


def test_retro_supports_more_than_two_notes_and_uses_box_art_framing():
    from margen.artwork import ArtworkRequest, image_prompt
    request, plan, _ = retro_fixture()
    for index in range(3):
        source = request.notes[0].model_copy(update={"id": f"extra{index}"})
        request.notes.append(source)
        plan.chapters[0].source_ids.append(source.id)
        plan.visuals.append(plan.visuals[-1].model_copy(update={"id": source.id, "source_ids": [source.id]}))
    plan = EditorialPlan.model_validate(plan.model_dump()).verify_visuals(request)
    assert len(plan.visuals) == len(request.notes) + 1
    prompt = image_prompt(ArtworkRequest(title=plan.title, visual=plan.visuals[1], sources=[request.notes[1]]))
    assert "Portrait 3:4" in prompt and "box-cover" in prompt


def test_service_version_matches_release_metadata(client):
    from margen import __version__
    from pathlib import Path
    manifest = json.loads((Path(__file__).resolve().parents[2] / "manifest.json").read_text())
    assert app.version == __version__ == manifest["version"]
    assert client.get("/health").json()["version"] == __version__
    assert client.get("/v1/library", headers=AUTH).json()["version"] == __version__


def test_oversized_job_explains_rejection_without_echoing_notes(client):
    payload = {"notes": [{"id": str(i), "path": f"{i}.md", "title": "Nota",
                           "markdown": "PRIVATE_NOTE" + "x" * 160_000} for i in range(4)]}
    response = client.post("/v1/jobs", headers=AUTH, json={"id": str(uuid.uuid4()), "publication": payload})
    assert response.status_code == 422
    assert "600.000" in response.json()["detail"]
    assert "PRIVATE_NOTE" not in response.text
    assert len(response.content) < 1000


def test_invalid_field_returns_explanation_without_input(client):
    payload = {**PAYLOAD, "title": "PRIVATE_TITLE" * 20}
    response = client.post("/v1/publications", headers=AUTH, json=payload)
    assert response.status_code == 422
    assert "title" in response.json()["detail"] and "160" in response.json()["detail"]
    assert "PRIVATE_TITLE" not in response.text


def test_retro_frames_note_images_without_changing_them(tmp_path):
    from PIL import Image
    from margen.epub import build_epub
    source = Image.new("RGB", (120, 40), "white")
    for x in range(0, 120, 7):
        source.putpixel((x, x % 40), (200, 30, 30))
    stream = io.BytesIO()
    source.save(stream, format="WEBP", lossless=True)
    big = io.BytesIO()
    Image.new("RGB", (900, 300), "blue").save(big, format="JPEG")
    markdown = ("Texto.\n\n![Esquema o captura](margen-asset:small)\n\n"
                "![Router con dos interfaces](margen-asset:large)")
    notes = [{"id": "a", "title": "Redes", "path": "a.md", "markdown": markdown}]
    assets = [{"id": "small", "media_type": "image/webp", "data": base64.b64encode(stream.getvalue()).decode()},
              {"id": "large", "media_type": "image/jpeg", "data": base64.b64encode(big.getvalue()).decode()}]
    request, plan, art = retro_fixture()
    request = PublicationRequest(notes=notes, assets=assets, style="retro90", artwork="generated")
    plan = EditorialPlan(title="Redes", subtitle="", chapters=[{"title": "Uno", "source_ids": ["a"]}],
                         visuals=[v.model_copy(update={"source_ids": ["a"]}) for v in (plan.visuals[0], plan.visuals[2])])
    illustrations = [{**v.model_dump(), "data": art, "media_type": "image/jpeg"} for v in plan.visuals]
    record = build_epub(request, plan, str(uuid.uuid4()), tmp_path / "retro", illustrations)
    with zipfile.ZipFile(tmp_path / "retro" / record["filename"]) as book:
        from margen.epub import frame_sizes
        framed = Image.open(io.BytesIO(book.read("EPUB/assets/small.png")))
        edge = sum(frame_sizes(480))  # whole factor 4, at most 4
        picture = framed.crop((edge, edge, edge + 480, edge + 160))
        # The frame surrounds the picture; nearest neighbour only repeats its pixels.
        assert framed.size == (480 + 2 * edge, 160 + 2 * edge)
        assert picture.resize((120, 40), Image.NEAREST).tobytes() == source.tobytes()
        large = Image.open(io.BytesIO(book.read("EPUB/assets/large.jpg")))
        assert large.size == (900 + 2 * sum(frame_sizes(900)), 300 + 2 * sum(frame_sizes(900)))
        article = book.read("EPUB/text/n_a.xhtml").decode()
        figures = etree.fromstring(article.encode()).xpath("//*[@class='retro-figure']")
        assert len(figures) == 2 and all(f[0].tag.endswith("img") and f[1].tag.endswith("br") for f in figures)
        assert "FIG. 01</span></p>" in article and "FIG. 02</span> · Router con dos interfaces" in article
        assert 'class="figure"' not in article
    study = build_epub(PublicationRequest(notes=notes, assets=assets), plan_publication(PublicationRequest(notes=notes, assets=assets)),
                       str(uuid.uuid4()), tmp_path / "study")
    with zipfile.ZipFile(tmp_path / "study" / study["filename"]) as book:
        # WebP becomes PNG for e-readers, pixel for pixel.
        assert Image.open(io.BytesIO(book.read("EPUB/assets/small.png"))).tobytes() == source.tobytes()
        assert "EPUB/assets/small.webp" not in book.namelist()
        article = book.read(f"EPUB/text/n_a.xhtml").decode()
        assert 'class="figure"' in article and "retro-figure" not in article
