"""The staged editor splits large selections and keeps rewritten content faithful."""
import pytest
from fastapi.testclient import TestClient

from margen import editor
from margen.editor import plan_publication, split_markdown, missing_tokens
from margen.models import PublicationRequest

SECTION = "## Subredes\n\nA máscara 255.255.255.0 deixa 254 equipos.\n\n```sh\nip addr add 192.168.1.10/24 dev eth0\n```\n\n" + "Texto explicativo. " * 300


def note(identifier, markdown):
    return {"id": identifier, "title": f"Nota {identifier}", "path": f"{identifier}.md", "markdown": markdown}


def outline(request, **extra):
    return {"title": "Redes", "subtitle": "", "visuals": [], "briefs": [{"source_id": n.id, "title": n.title, "summary": "", "connections": []} for n in request.notes],
            "chapters": [{"title": "Todo", "source_ids": [n.id for n in request.notes]}], **extra}


@pytest.fixture
def ai(monkeypatch):
    monkeypatch.setattr(editor, "ai_available", lambda: True)
    monkeypatch.setenv("AI_CHUNK_CHARS", "8000")
    calls = []
    def install(write):
        def complete(stage, instructions, payload, schema):
            calls.append((stage, payload))
            return outline(current["request"]) if stage == "plan" else write(payload)
        monkeypatch.setattr(editor, "complete", complete)
        return calls
    current = {}
    install.current = current
    return install


def test_split_never_cuts_code_and_prefers_headings():
    code = "```sh\n" + "\n\n".join(f"echo {i}" for i in range(400)) + "\n```"
    text = "## Uno\n\n" + "Frase. " * 900 + "\n\n## Dous\n\n" + code + "\n\n## Tres\n\nFinal."
    parts = split_markdown(text, 4000)
    assert " ".join("\n\n".join(parts).split()) == " ".join(text.split())
    assert all(p.count("```") % 2 == 0 for p in parts)
    assert all(len(p) <= 4100 for p in parts if "```" not in p)
    assert any(p.startswith("## Dous\n\n```sh") for p in parts)
    assert not any(p.rstrip().endswith(("## Uno", "## Dous", "## Tres")) for p in parts)


def test_large_note_is_written_in_parts_and_joined_in_order(ai):
    request = PublicationRequest(notes=[note("a", SECTION * 4), note("b", "Breve.")], writing_mode="narrative")
    ai.current["request"] = request
    calls = ai(lambda payload: {"markdown": f"Parte {payload['part']['number']}/{payload['part']['total']} "
                                            + " ".join(sorted(editor.required_tokens(payload["source"]))), "aids": ""})
    plan = plan_publication(request)
    writes = [p for stage, p in calls if stage == "write"]
    assert len([p for p in writes if p["article"]["source_id"] == "a"]) >= 3
    assert all(len(p["source"]) <= 9000 for p in writes)
    article = plan.articles[0].markdown
    assert article.index("Parte 1/") < article.index("Parte 2/")
    assert all(p["previous_context"] for p in writes if p["part"]["number"] > 1)


def test_outline_digests_large_selections_and_retries_invalid_plans(ai, monkeypatch):
    request = PublicationRequest(notes=[note("a", SECTION * 12), note("b", "Breve.")])
    request.use_ai = True
    payloads = []
    def complete(stage, instructions, payload, schema):
        payloads.append(payload)
        ids = ["a"] if len(payloads) == 1 else ["a", "b"]
        return {"title": "Redes", "subtitle": "", "visuals": [], "briefs": [{"source_id": n.id, "title": n.title, "summary": "", "connections": []} for n in request.notes],
                "chapters": [{"title": "Todo", "source_ids": ids}]}
    monkeypatch.setattr(editor, "complete", complete)
    plan = plan_publication(request)
    assert plan.chapters[0].source_ids == ["a", "b"]
    assert "markdown" not in payloads[0]["notes"][0] and payloads[0]["notes"][0]["headings"]
    assert "exactamente una vez" in payloads[1]["previous_error"]


def test_missing_data_triggers_one_rewrite_with_the_missing_items(ai):
    request = PublicationRequest(notes=[note("a", SECTION)], writing_mode="simple")
    ai.current["request"] = request
    def write(payload):
        if "missing" in payload:
            return {"markdown": "Agora completo: " + " ".join(payload["missing"]), "aids": ""}
        return {"markdown": "Versión sen datos.", "aids": ""}
    calls = ai(write)
    plan = plan_publication(request)
    retried = [p for stage, p in calls if stage == "write" and "missing" in p]
    assert retried and "255.255.255.0" in retried[0]["missing"]
    assert not missing_tokens(SECTION, plan.articles[0].markdown)


def test_finished_parts_are_reused_after_a_failure(ai, tmp_path):
    request = PublicationRequest(notes=[note("a", "Texto A."), note("b", "Texto B.")], writing_mode="review")
    ai.current["request"] = request
    failing = {"b": True}
    def write(payload):
        if failing.get(payload["article"]["source_id"]):
            raise ValueError("Codex ha agotado el tiempo de una parte de la edición.")
        return {"markdown": "Resumo de " + payload["article"]["source_id"], "aids": ""}
    calls = ai(write)
    with pytest.raises(ValueError, match="se reutilizarán"):
        plan_publication(request, tmp_path)
    failing["b"] = False
    calls.clear()
    plan = plan_publication(request, tmp_path)
    assert [p["article"]["source_id"] for stage, p in calls if stage == "write"] == ["b"]
    assert [a.markdown for a in plan.articles] == ["Resumo de a", "Resumo de b"]


def test_bridge_rejects_unsafe_model_arguments(monkeypatch):
    from margen.bridge import app
    token = "x" * 40
    monkeypatch.setenv("MARGEN_TOKEN", token)
    monkeypatch.setattr("margen.bridge.codex_complete", lambda *args: {"ok": args[3:5]})
    client = TestClient(app)
    headers = {"Authorization": "Bearer " + token}
    body = {"instructions": "x", "input": {}, "output_schema": {}, "model": "gpt-x", "effort": "high"}
    assert client.post("/v1/complete", headers=headers, json=body).json() == {"ok": ["gpt-x", "high"]}
    for unsafe in [{"model": "a b"}, {"model": "--config=x"}, {"model": "--sandbox"}, {"effort": 'high"; x="'}]:
        assert client.post("/v1/complete", headers=headers, json={**body, **unsafe}).status_code == 422
    assert client.post("/v1/complete", json=body).status_code == 401


def test_untagged_blocks_only_require_their_data():
    source = "```\nMAC Porto Tempo\nP 1 10:00:12\n```\n\n```sh\nip route show\n```"
    written = "| MAC | Puerto | Tiempo |\n|---|---|---|\n| P | 1 | 10:00:12 |\n\n```sh\nip route show\n```"
    assert missing_tokens(source, written) == []
    assert missing_tokens(source, "| P | 1 | 10:00:12 |") == ["ip route show"]


def test_pasted_blobs_are_not_required_data():
    blob = "u2lWj6/EI/dozvKuY0BYoK2n71zVT4gxbVTT4mHbkmI51v3R5OwNO+uQa+RCf2615RTrevhH4uYrIbe"
    assert missing_tokens(f"Porto 8080.\n\n{blob}", "Puerto 8080.") == []
