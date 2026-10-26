import base64
import io
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
import pytest
from PIL import Image
from margen import artwork
from margen.models import Asset, Source, VisualBrief


def test_invalid_image_and_excessive_dimensions_are_rejected():
    with pytest.raises(ValueError):Asset(id='a',media_type='image/png',data=base64.b64encode(b'\x89PNG\r\n\x1a\ninvalid').decode())
    stream=io.BytesIO();Image.new('RGB',(20001,1),'white').save(stream,format='PNG')
    with pytest.raises(ValueError,match='20.000'):Asset(id='a',media_type='image/png',data=base64.b64encode(stream.getvalue()).decode())


@pytest.mark.parametrize('foreign',[False,True])
def test_artwork_only_reads_and_cleans_its_own_session(tmp_path,monkeypatch,foreign):
    monkeypatch.setattr(Path,'home',classmethod(lambda cls:tmp_path))
    monkeypatch.setenv('CODEX_HOME',str(tmp_path/'.codex'));monkeypatch.setenv('CODEX_BIN','synthetic-codex')
    thread=str(uuid.uuid4());directory=tmp_path/'.codex/generated_images'/thread;directory.mkdir(parents=True)
    other=tmp_path/'.codex/generated_images/other.png';Image.new('RGB',(32,32),'white').save(other)
    own=directory/'own.png'
    if not foreign:Image.new('RGB',(32,32),'white').save(own)
    def run(args,**kwargs):
        if 'login' in args:return SimpleNamespace(returncode=0,stdout='Logged in using ChatGPT',stderr='')
        Path(args[args.index('-o')+1]).write_text(json.dumps({'image_path':str(other if foreign else own)}))
        return SimpleNamespace(returncode=0,stdout=json.dumps({'type':'thread.started','thread_id':thread}),stderr='')
    monkeypatch.setattr(artwork.subprocess,'run',run)
    request=artwork.ArtworkRequest(title='Test',visual=VisualBrief(id='cover',placement='cover',source_ids=['a'],concept='Test',description='Test',caption=''),
        sources=[Source(id='a',path='a.md',title='Test',markdown='Synthetic.')])
    if foreign:
        with pytest.raises(ValueError,match='esta sesión'):artwork.codex_artwork(request)
    else:
        assert artwork.codex_artwork(request)['media_type']=='image/jpeg'
        assert not own.exists()
    assert other.exists()
