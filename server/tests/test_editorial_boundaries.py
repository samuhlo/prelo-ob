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


@pytest.mark.parametrize('source', [
    'Valor `-5`.', 'Valor `+5`.', 'Puerto `8080`.', 'Versión v1.2.3; eth0.1.',
    'Servidor http://127.0.0.1:8080/ruta/42.', 'IPv6: 2001:db8::1.',
    'Valores: -5, +5, 1.25 y 3/4; 2026-10-28.',
])
def test_literal_guard_is_reflexive_in_code_and_prose(source):
    assert editor.missing_tokens(source, source) == []


@pytest.mark.parametrize('written', [
    '![Esquema](margen-asset:asset1.png)', '![Esquema](margen-asset:asset1#fragment)',
    '![Esquema](margen-asset:asset1/extra)', 'La imagen era margen-asset:asset1.',
])
def test_asset_guard_matches_the_renderers_whole_image_destination(written):
    source = '![Esquema](margen-asset:asset1)'
    assert editor.missing_assets(source, written) == ['margen-asset:asset1']
