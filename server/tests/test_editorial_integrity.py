import pytest
from margen import editor
from margen.models import PublicationRequest, Outline


def request(markdown='El puerto es 8080; hay 5 equipos. Ejecuta `ip route show`.',mode='simple'):
    return PublicationRequest(writing_mode=mode,notes=[dict(id='a',path='a.md',title='Redes',markdown=markdown)])


def outline():
    return dict(title='Redes',subtitle='',chapters=[dict(title='Redes',source_ids=['a'])],briefs=[dict(source_id='a',title='Redes',summary='',connections=[])])


@pytest.mark.parametrize('source,written,missing',[
    ('Hai 5 equipos.', 'Hay 15 equipos.', '5'),
    ('El puerto es 8080.', 'El puerto es 18080.', '8080'),
    ('Temperatura: -5.', 'Temperatura: 5.', '-5'),
    ('![Diagrama](margen-asset:'+'a'*64+')', 'Sin imagen.', 'margen-asset:'+'a'*64),
])
def test_critical_literals_cannot_be_hidden_inside_other_values(source,written,missing):
    assert missing in editor.missing_tokens(source,written)
    assert editor.missing_tokens(source,source)==[]


def test_failed_rewrite_is_rejected_after_one_retry(monkeypatch,tmp_path):
    calls=[]
    def complete(stage,instructions,payload,schema):
        calls.append(stage)
        return outline() if stage=='plan' else {'markdown':'Una red conecta equipos.','aids':''}
    monkeypatch.setattr(editor,'ai_available',lambda:True);monkeypatch.setattr(editor,'complete',complete)
    with pytest.raises(ValueError,match='No se ha publicado'):editor.plan_publication(request(),tmp_path)
    assert calls.count('write')==2
    assert len(list(tmp_path.glob('*.json')))==1  # Only the valid outline stays cached.


def test_review_may_condense_but_cannot_drop_an_image(monkeypatch):
    monkeypatch.setattr(editor,'ai_available',lambda:True)
    monkeypatch.setattr(editor,'complete',lambda stage,*_:outline() if stage=='plan' else {'markdown':'Resumen.','aids':''})
    with pytest.raises(ValueError,match='No se ha publicado'):
        editor.plan_publication(request('![Esquema](margen-asset:asset1)',mode='review'))


@pytest.mark.parametrize('briefs',[[],[dict(source_id='b',title='Unknown',summary='',connections=[])]])
def test_incomplete_briefs_are_not_written(monkeypatch,briefs):
    calls=[]
    def complete(stage,*_):calls.append(stage);return {**outline(),'briefs':briefs}
    monkeypatch.setattr(editor,'ai_available',lambda:True);monkeypatch.setattr(editor,'complete',complete)
    with pytest.raises(ValueError,match='ficha editorial'):editor.plan_publication(request())
    assert calls==['plan','plan']


def test_cache_does_not_reuse_another_provider(monkeypatch,tmp_path):
    cache=editor.Cache(tmp_path);calls=[]
    monkeypatch.setattr(editor,'complete',lambda *args:calls.append(1) or {'answer':'ok'})
    monkeypatch.setenv('AI_PROVIDER','provider-a');cache.call('write','instructions',{},{});cache.call('write','instructions',{}, {})
    monkeypatch.setenv('AI_PROVIDER','provider-b');cache.call('write','instructions',{}, {})
    assert len(calls)==2
