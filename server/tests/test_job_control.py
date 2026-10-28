import base64
import threading
import uuid
import pytest
from margen import artwork, jobs, library, editor
from margen.models import PublicationRequest, EditorialPlan


def test_images_do_not_start_after_cancellation(tmp_path, monkeypatch):
    notes=[dict(id=f'n{i}',path=f'{i}.md',title='Topic',markdown='Synthetic.') for i in range(5)]
    request=PublicationRequest(notes=notes,style='retro90',artwork='generated')
    visuals=[dict(id='cover',placement='cover',source_ids=['n0'],concept='Cover',description='Scene',caption='')]+[
        dict(id=f'inside{i}',placement='inside',source_ids=[n['id']],concept='Topic',description='Scene',caption='') for i,n in enumerate(notes)]
    plan=EditorialPlan(title='Test',subtitle='',chapters=[dict(title='Topic',source_ids=[n['id'] for n in notes])],visuals=visuals)
    cancelled=threading.Event(); after=[]
    def generate(job, cancelled_check=lambda: False):
        after.append(cancelled.is_set())
        if job.visual.id=='cover': assert cancelled.wait(2)
        return {'data':base64.b64encode(b'\xff\xd8\xffsynthetic').decode(),'media_type':'image/jpeg'}
    def progress(message):
        if message.startswith('Ilustraciones: 1 '): cancelled.set()
        if cancelled.is_set(): raise jobs.Cancelled()
    monkeypatch.setenv('AI_PROVIDER','codex-cli');monkeypatch.setattr(artwork,'codex_artwork',generate)
    with pytest.raises(jobs.Cancelled): artwork.generate_visuals(request,plan,tmp_path,progress,cancelled.is_set)
    assert not any(after) and len(after)<=3


def test_job_admission_is_bounded_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv('MARGEN_MAX_JOBS','1')
    release=threading.Event(); started=threading.Event()
    request=PublicationRequest(notes=[dict(id='a',path='a.md',title='A',markdown='Test')])
    def build(request,identity,progress,cancelled):
        started.set(); release.wait(2); return {'id':identity}
    identity=str(uuid.uuid4())
    try:
        jobs.submit(tmp_path,identity,request,build);assert started.wait(2)
        assert jobs.submit(tmp_path,identity,request,build)['id']==identity
        with pytest.raises(jobs.QueueFull): jobs.submit(tmp_path,str(uuid.uuid4()),request,build)
    finally: release.set()


def test_absent_reader_file_is_not_reported_imported():
    record={'id':'a','delivery':'sent','delivered_at':'2026-01-01'}
    assert library.on_kobo(record,{'a':{'present':False}},{'at':'2026-02-01'})=='missing'


def test_text_provider_rejects_artwork_before_any_paid_call(monkeypatch):
    monkeypatch.setenv('AI_PROVIDER','compatible');monkeypatch.setattr(editor,'ai_available',lambda:True)
    monkeypatch.setattr(editor,'make_outline',lambda *_:pytest.fail('Must not invoke planning'))
    request=PublicationRequest(style='retro90',artwork='generated',notes=[dict(id='a',path='a.md',title='A',markdown='Test')])
    with pytest.raises(ValueError,match='solo genera texto'):editor.plan_publication(request)


import pytest
from margen import jobs
from margen.models import PublicationRequest


def test_failed_persistence_does_not_permanently_fill_admission(tmp_path, monkeypatch):
    subject = jobs
    monkeypatch.setenv("MARGEN_MAX_JOBS", "1")
    monkeypatch.setattr(subject, "ACTIVE", set())
    monkeypatch.setattr(subject, "CANCELLED", set())

    class PendingExecutor:
        def submit(self, fn):
            return None

    monkeypatch.setattr(subject, "POOL", PendingExecutor())
    request = PublicationRequest(notes=[dict(id="a", path="a.md", title="A", markdown="A")])
    original_write = subject.write

    def disk_full(*args):
        raise OSError("Synthetic disk full")

    monkeypatch.setattr(subject, "write", disk_full)
    with pytest.raises(OSError, match="Synthetic disk full"):
        subject.submit(tmp_path, "00000000-0000-4000-8000-000000000001", request, lambda *args: None)
    monkeypatch.setattr(subject, "write", original_write)
    try:
        result = subject.submit(tmp_path, "00000000-0000-4000-8000-000000000002", request, lambda *args: None)
    except ValueError as error:
        pytest.fail(f"A job that was never persisted permanently occupies admission: {error}")
    assert result["state"] == "queued"


def test_rejected_executor_releases_admission_even_if_failure_cannot_be_saved(tmp_path, monkeypatch):
    class RejectedExecutor:
        def submit(self, fn):
            raise RuntimeError('Synthetic executor stopped')
    monkeypatch.setattr(jobs, 'POOL', RejectedExecutor())
    monkeypatch.setattr(jobs, 'ACTIVE', set())
    monkeypatch.setattr(jobs, 'CANCELLED', set())
    request = PublicationRequest(notes=[dict(id='a', path='a.md', title='A', markdown='A')])
    identity = str(uuid.uuid4())
    with pytest.raises(RuntimeError, match='executor stopped'):
        jobs.submit(tmp_path, identity, request, lambda *args: pytest.fail('Must not run'))
    assert not jobs.ACTIVE
    assert not jobs.CANCELLED
    assert jobs.read(tmp_path, identity)['state'] == 'failed'
