import json
import uuid
import subprocess
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from margen import artwork, jobs
from margen.models import EditorialPlan, PublicationRequest


def test_images_waiting_for_a_codex_slot_do_not_start_after_cancel(tmp_path, monkeypatch):
    cancelled = threading.Event()
    all_acquiring = threading.Event()
    starts = []

    class Slots:
        def __init__(self):
            self.semaphore = threading.BoundedSemaphore(1)
            self.lock = threading.Lock()
            self.attempts = 0

        def acquire(self, timeout):
            with self.lock:
                self.attempts += 1
                if self.attempts == 3:
                    all_acquiring.set()
            return self.semaphore.acquire(timeout=timeout)

        def release(self):
            self.semaphore.release()

    def run(args, **kwargs):
        if args[1] == 'login':
            return SimpleNamespace(returncode=0, stdout='using ChatGPT', stderr='')
        starts.append(cancelled.is_set())
        if len(starts) == 1:
            assert all_acquiring.wait(3)
            cancelled.set()
        answer = Path(args[args.index('-o') + 1])
        thread = str(uuid.uuid5(uuid.NAMESPACE_URL, str(answer)))
        image = tmp_path.resolve() / 'generated_images' / thread / 'synthetic.jpg'
        image.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (8, 8)).save(image)
        answer.write_text(json.dumps({'image_path': str(image)}))
        return SimpleNamespace(returncode=0, stdout=json.dumps({'type': 'thread.started', 'thread_id': thread}), stderr='')

    def progress(message):
        if cancelled.is_set():
            raise jobs.Cancelled()

    monkeypatch.setenv('AI_PROVIDER', 'codex-cli')
    monkeypatch.setenv('CODEX_BIN', 'synthetic-codex')
    monkeypatch.setenv('CODEX_HOME', str(tmp_path.resolve()))
    monkeypatch.setenv('AI_IMAGE_CONCURRENCY', '3')
    monkeypatch.setattr(artwork, 'SLOTS', Slots())
    monkeypatch.setattr(subprocess, 'run', run)
    notes = [dict(id=f'n{i}', path=f'{i}.md', title='Topic', markdown='Synthetic.') for i in range(2)]
    request = PublicationRequest(notes=notes, style='retro90', artwork='generated')
    visuals = [dict(id='cover', placement='cover', source_ids=['n0'], concept='Cover', description='Scene', caption='')]
    visuals += [dict(id=f'inside{i}', placement='inside', source_ids=[n['id']], concept='Topic', description='Scene', caption='') for i, n in enumerate(notes)]
    plan = EditorialPlan(title='Test', subtitle='', chapters=[dict(title='Topic', source_ids=['n0', 'n1'])], visuals=visuals)
    with pytest.raises(jobs.Cancelled):
        artwork.generate_visuals(request, plan, tmp_path / 'cache', progress, cancelled.is_set)
    assert artwork.SLOTS.semaphore.acquire(blocking=False), 'The cancelled waiter leaked a slot'
    artwork.SLOTS.semaphore.release()
    assert starts == [False], f'Paid generations started after cancellation: {starts}'
