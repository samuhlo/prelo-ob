import pytest

from margen import editor
from margen.models import PublicationRequest


def install_ai(monkeypatch, source, written, mode="simple", assets=()):
    request = PublicationRequest(
        writing_mode=mode,
        notes=[dict(id="a", path="a.md", title="Prueba", markdown=source)],
        assets=list(assets),
    )
    outline = dict(
        title="Prueba",
        subtitle="",
        chapters=[dict(title="Prueba", source_ids=["a"])],
        briefs=[dict(source_id="a", title="Prueba", summary="", connections=[])],
    )
    monkeypatch.setattr(editor, "ai_available", lambda: True)
    monkeypatch.setattr(
        editor,
        "complete",
        lambda stage, *_: outline if stage == "plan" else dict(markdown=written, aids=""),
    )
    return request


@pytest.mark.parametrize("source", ["Versión v1.2.3.", "Interfaz eth0.1 activa.", "Servidor: http://127.0.0.1:8080/"]) 
def test_unchanged_identifiers_are_not_rejected(monkeypatch, source):
    request = install_ai(monkeypatch, source, source)
    plan = editor.plan_publication(request)
    assert plan.articles[0].markdown == source


def test_positive_value_cannot_be_replaced_by_negative(monkeypatch):
    request = install_ai(monkeypatch, "Temperatura: 5.", "Temperatura: -5.")
    with pytest.raises(ValueError, match="No se ha publicado"):
        editor.plan_publication(request)


def test_review_cannot_replace_image_with_id_prefix(monkeypatch):
    request = install_ai(
        monkeypatch,
        "![Esquema](margen-asset:asset1)",
        "![Esquema](margen-asset:asset12)",
        mode="review",
        assets=[dict(
            id="asset1",
            media_type="image/png",
            data="iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFUlEQVR4nGP8//8/AzbAhFV00EoAAFbUAw037MyjAAAAAElFTkSuQmCC",
        )],
    )
    from margen.epub import render_note

    original, _ = render_note(request.notes[0], {}, {"asset1": "asset1.png"}, [])
    assert "<img" in original
    with pytest.raises(ValueError, match="No se ha publicado"):
        editor.plan_publication(request)
