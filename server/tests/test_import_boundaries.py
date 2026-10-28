import json
import uuid

import yaml
from fastapi.testclient import TestClient
from margen.app import app
from margen.native import append_notes


def quote(key="a", source=None):
    return dict(key=key * 64, text="Quote", annotation="", source=source,
                match="chapter" if source else "book", volume_id="book.epub",
                title="Book", author="", created_at="")


def test_unrelated_invalid_date_does_not_abort_import(tmp_path):
    (tmp_path / "unrelated.md").write_text("---\ndate: 2026-02-30\n---\nUnrelated note.")
    error = None
    try:
        result = append_notes(tmp_path, "Quotes", [quote()])
    except Exception as caught:
        error = caught
    assert error is None, f"An unrelated note aborted the import: {error!r}"
    assert result["added"] == 1


def test_commented_identity_does_not_split_damaged_note(tmp_path):
    identity = str(uuid.uuid4())
    source = dict(id=identity, title="Source", path="missing.md")
    folder = tmp_path / "Quotes"
    folder.mkdir()
    original = folder / "existing.md"
    original.write_text(f'---\nmargen_lectura: "{identity}" # reader identity\n---\nPersonal comments.\n')
    append_notes(tmp_path, "Quotes", [quote(source=source)])
    healthy = original.read_text()
    damaged = healthy.replace("\n---\n", "\ninvalid: [\n---\n", 1)
    original.write_text(damaged)
    try:
        append_notes(tmp_path, "Quotes", [quote("b", source)])
    except (ValueError, yaml.YAMLError):
        pass
    assert original.read_text() == damaged
    note_count = len(list(folder.glob("*.md")))
    original.write_text(healthy)
    result = append_notes(tmp_path, "Quotes", [quote("c", source)])
    assert note_count == 1, "A second note was created for the damaged note's existing identity"
    assert result["added"] == 1, "Repairing the original note should allow later quotes to import"


def test_renamed_source_with_large_valid_frontmatter_keeps_link(tmp_path):
    identity = str(uuid.uuid4())
    renamed = tmp_path / "renamed.md"
    renamed.write_text(f"---\nmargen_id: {identity}\ndescription: " + "x" * 17000 + "\n---\nSource text.")
    source = dict(id=identity, title="Source", path="old-name.md")
    result = append_notes(tmp_path, "Quotes", [quote(source=source)])
    imported = next((tmp_path / "Quotes").glob("*.md")).read_text()
    assert "[[renamed]]" in imported, "A valid stable identity was lost because the YAML closing delimiter is beyond 16 KiB"
    assert result["unresolved"] == 0


def test_corrupt_then_repaired_manifest_does_not_duplicate_quote(tmp_path, monkeypatch):
    root, vault = tmp_path / "service", tmp_path / "vault"
    vault.mkdir()
    token = "x" * 32
    monkeypatch.setenv("MARGEN_DATA", str(root))
    monkeypatch.setenv("MARGEN_TOKEN", token)
    client = TestClient(app, raise_server_exceptions=False)
    headers = {"Authorization": "Bearer " + token}
    response = client.post("/v1/publications", headers=headers, json={"notes": [dict(id="a", path="source.md", title="Source", markdown="Quote")]})
    assert response.status_code == 201, response.text
    publication = response.json()
    manifest = root / publication["id"] / "manifest.json"
    healthy = manifest.read_text()
    raw = dict(id="bookmark", volume_id=publication["filename"], content_id="text/n_a.xhtml", text="Quote")
    manifest.write_text("{")
    response = client.post("/v1/annotations", headers=headers, json={"highlights": [raw]})
    if response.status_code == 200:
        append_notes(vault, "Quotes", response.json()["highlights"])
    manifest.write_text(healthy)
    response = client.post("/v1/annotations", headers=headers, json={"highlights": [raw]})
    assert response.status_code == 200, response.text
    append_notes(vault, "Quotes", response.json()["highlights"])
    marker = "<!-- margen:" + response.json()["highlights"][0]["key"] + ":"
    copies = sum(path.read_text().count(marker) for path in (vault / "Quotes").glob("*.md"))
    assert copies == 1, f"Repairing the manifest left {copies} copies of one unchanged Kobo quote"


def test_null_anchor_does_not_break_resolution(tmp_path, monkeypatch):
    token = "x" * 32
    monkeypatch.setenv("MARGEN_DATA", str(tmp_path))
    monkeypatch.setenv("MARGEN_TOKEN", token)
    client = TestClient(app, raise_server_exceptions=False)
    headers = {"Authorization": "Bearer " + token}
    response = client.post("/v1/publications", headers=headers, json={"notes": [dict(id="a", path="source.md", title="Source", markdown="Quote")]})
    assert response.status_code == 201, response.text
    publication = response.json()
    manifest = tmp_path / publication["id"] / "manifest.json"
    value = json.loads(manifest.read_text())
    value["sources"][0]["anchor"] = None
    manifest.write_text(json.dumps(value))
    response = client.post("/v1/highlights/resolve", headers=headers, json={"highlights": [dict(id="bookmark", volume_id=publication["filename"], content_id="text/n_a.xhtml", text="Quote")]})
    assert response.status_code == 200, f"An unchecked null anchor breaks the whole resolution request: {response.status_code}"


def test_quote_updates_stay_in_the_existing_note_after_provenance_recovers(tmp_path):
    first = quote()
    append_notes(tmp_path, "Quotes", [first])
    original = next((tmp_path / "Quotes").glob("*.md"))
    original.write_text(original.read_text() + "\nPersonal comment.\n")
    resolved = {**first, "source": dict(id=str(uuid.uuid4()), title="Source", path="missing.md"), "match": "chapter"}
    assert append_notes(tmp_path, "Quotes", [resolved])["added"] == 0
    resolved["annotation"] = "Updated on the reader"
    assert append_notes(tmp_path, "Quotes", [resolved])["added"] == 1
    assert len(list((tmp_path / "Quotes").glob("*.md"))) == 1
    assert "Personal comment." in original.read_text()
    assert "Updated on the reader" in original.read_text()
    assert append_notes(tmp_path, "Quotes", [resolved])["added"] == 0
