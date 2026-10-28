"""Explicit publication manifest. Adding a public file requires reviewing this list."""
from pathlib import Path

PUBLIC_FILES = set("""
.env.example
.github/RELEASE_NOTES.md
.github/workflows/ci.yml
.github/workflows/release.yml
.gitignore
AGENTS.md
CHANGELOG.md
Instalar Prelo.command
LICENSE
README.md
THIRD_PARTY_NOTICES.md
assets/LICENSE.anaco
assets/prelo-logo.svg
compose.yaml
docs/desarrollo.md
docs/beta-acceptance.json
docs/instalacion.md
docs/privacidad.md
docs/producto.md
docs/revista-90s.md
docs/validacion-publica.md
manifest.json
plugin/build.mjs
plugin/manifest.json
plugin/package-lock.json
plugin/package.json
plugin/src/assets.d.ts
plugin/src/brand.ts
plugin/src/core.ts
plugin/src/delivery.ts
plugin/src/editorial.ts
plugin/src/installation.ts
plugin/src/connection.ts
plugin/src/main.ts
plugin/src/reader.ts
plugin/src/selection.ts
plugin/src/session.ts
plugin/src/sqlite.ts
plugin/src/studio.ts
plugin/src/updates.ts
plugin/styles.css
plugin/tests/core.test.ts
plugin/tests/delivery.test.ts
plugin/tests/distribution.test.mjs
plugin/tests/draft-recovery.test.ts
plugin/tests/editorial.test.ts
plugin/tests/reader.test.ts
plugin/tests/selection.test.ts
plugin/tests/session.test.ts
plugin/tests/updates.test.ts
plugin/tests/installation.test.ts
plugin/tests/connection.test.ts
plugin/tests/validation.test.ts
plugin/tsconfig.json
scripts/audit_public.py
scripts/build_release.py
scripts/check_caption_layout.py
scripts/install.py
scripts/install_transaction.py
scripts/install_bridge.py
scripts/install_common.py
scripts/install_plugin.py
scripts/install_usb.py
scripts/public_files.py
scripts/publish_local.py
scripts/render_cover.mjs
scripts/restore_backup.py
scripts/run_bridge.py
scripts/set_version.py
scripts/setup.py
scripts/check_beta.py
scripts/fetch_epubcheck.py
scripts/smoke_service.py
scripts/validate_epub.py
server/.dockerignore
server/Dockerfile
server/margen/__init__.py
server/margen/app.py
server/margen/artwork.py
server/margen/bridge.py
server/margen/codex_editor.py
server/margen/design.py
server/margen/editor.py
server/margen/epub.py
server/margen/highlights.py
server/margen/jobs.py
server/margen/kobo.py
server/margen/library.py
server/margen/models.py
server/margen/native.py
server/margen/prompts.py
server/pyproject.toml
server/requirements.lock
server/tests/test_command_safety.py
server/tests/test_editorial_integrity.py
server/tests/test_editorial_boundaries.py
server/tests/test_editorial_modes.py
server/tests/test_import_integrity.py
server/tests/test_import_boundaries.py
server/tests/test_job_control.py
server/tests/test_library_usb.py
server/tests/test_pipeline.py
server/tests/test_image_boundaries.py
server/tests/test_staged_editor.py
server/tests/test_storage_recovery.py
server/uv.lock
tests/test_installation.py
tests/test_install_recovery.py
tests/test_public_boundary.py
tests/test_versions.py
tests/test_beta_gate.py
versions.json
""".strip().splitlines())


def public_files(root):
    root = Path(root).resolve()
    result = []
    for name in sorted(PUBLIC_FILES):
        path = root / name
        parts = Path(name).parts
        if any(root.joinpath(*parts[:i]).is_symlink() for i in range(1, len(parts) + 1)):
            raise ValueError("A public source cannot be a symlink: " + name)
        if path.is_file():
            if not path.resolve().is_relative_to(root):
                raise ValueError("A public source escapes its root: " + name)
            result.append(path)
    return result
