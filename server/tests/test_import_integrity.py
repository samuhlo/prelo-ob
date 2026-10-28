import json
import uuid
import pytest
from fastapi.testclient import TestClient
from margen import library
from margen.app import app
from margen.native import append_notes
from margen.highlights import resolve
from margen.models import Highlight


def quote(source=None):
    return dict(key='a'*64,text='Quote',annotation='',source=source,match='chapter' if source else 'book',
                volume_id='book.epub',title='Book',author='',created_at='')


def test_bad_yaml_is_isolated_and_existing_groups_are_not_split(tmp_path):
    folder=tmp_path/'Quotes';folder.mkdir()
    bad=folder/'bad.md';bad.write_text('---\ninvalid: [\n---\nKeep this note.')
    result=append_notes(tmp_path,'Quotes',[quote()])
    assert result['added']==1 and len(result['issues'])==1
    identity=str(uuid.uuid4());source=dict(id=identity,title='Source',path='missing.md')
    original='---\nmargen_lectura: '+identity+'\ninvalid: [\n---\nKeep this too.'
    bad.write_text(original)
    result=append_notes(tmp_path,'Quotes',[quote(source)])
    assert result['skipped']==1 and result['added']==0 and bad.read_text()==original
    assert len(list(folder.glob('*.md')))==2


def test_body_example_never_assigns_source_identity(tmp_path):
    identity=str(uuid.uuid4())
    (tmp_path/'unrelated.md').write_text('Example:\n```yaml\nmargen_id: '+identity+'\n```')
    append_notes(tmp_path,'Quotes',[quote(dict(id=identity,title='Source',path='missing.md'))])
    text=next((tmp_path/'Quotes').glob('*.md')).read_text()
    assert '[[unrelated]]' not in text and 'pendiente de vincular' in text


def test_shared_xhtml_anchor_beats_repeated_quote():
    edition=str(uuid.uuid4())
    sources=[dict(id=i,title=i,path=i+'.md',sha256='a'*64,href='text/n_a.xhtml',anchor='n_'+i,text='same quote') for i in ['a','b']]
    result=resolve(Highlight(id='h',volume_id=f'margen-{edition}.epub',content_id='text/n_a.xhtml#n_b',text='same quote'),
                   {edition:dict(id=edition,title='Test',sources=sources)})
    assert result['source']['id']=='b' and result['match']=='anchor'


def test_corrupt_manifest_does_not_hide_other_editions(tmp_path,monkeypatch):
    monkeypatch.setenv('MARGEN_DATA',str(tmp_path));monkeypatch.setenv('MARGEN_TOKEN','x'*32)
    client=TestClient(app);headers={'Authorization':'Bearer '+'x'*32}
    good=client.post('/v1/publications',headers=headers,json={'notes':[dict(id='a',path='a.md',title='A',markdown='Test.')]}).json()
    identity=str(uuid.uuid4());broken=tmp_path/identity;broken.mkdir();(broken/'manifest.json').write_text('{')
    response=client.get('/v1/library',headers=headers)
    assert response.status_code==200
    assert response.json()['publications'][0]['id']==good['id']
    assert response.json()['issues']==[{'edition':identity,'kind':'invalid_manifest'}]
    assert client.get(f'/v1/publications/{identity}',headers=headers).status_code==409
    with pytest.raises(ValueError,match='fichas dañadas'):library.backup(tmp_path)
