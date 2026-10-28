import importlib.util
from pathlib import Path
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from public_files import public_files
from audit_public import audit


def test_private_files_are_not_included_even_inside_source_folders(tmp_path):
    for name in ['server/connection.json','plugin/usb.json','assets/private.txt','server/service.env','tests/notes.md']:
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('synthetic private material')
    assert public_files(tmp_path)==[] and audit(tmp_path)==[]


def test_known_public_files_are_included(tmp_path):
    (tmp_path/'server/margen').mkdir(parents=True)
    (tmp_path/'server/margen/app.py').write_text('# synthetic source')
    assert [p.relative_to(tmp_path).as_posix() for p in public_files(tmp_path)]==['server/margen/app.py']


def test_symlinks_are_rejected_for_explicit_entries(tmp_path):
    target=tmp_path/'private';target.write_text('synthetic')
    try:(tmp_path/'README.md').symlink_to(target)
    except OSError:pytest.skip('Symlink creation is unavailable on this platform')
    with pytest.raises(ValueError,match='symlink'):public_files(tmp_path)


def test_installer_filename_with_spaces_is_kept(tmp_path):
    (tmp_path/'Instalar Prelo.command').write_text('# synthetic launcher')
    assert [p.name for p in public_files(tmp_path)]==['Instalar Prelo.command']
