import hashlib
import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient
from margen import __version__, service_update, updater
from margen.app import app

TOKEN = "update-test-" + "x" * 32
AUTH = {"Authorization": "Bearer " + TOKEN}
major, minor, patch = map(int, __version__.split("."))
NEWER = f"{major}.{minor}.{patch + 1}"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MARGEN_DATA", str(tmp_path / "service"))
    monkeypatch.setenv("MARGEN_TOKEN", TOKEN)
    return TestClient(app)


def heartbeat(client, updater=True, state="disconnected"):
    return client.post("/v1/device", headers=AUTH, json={"state": state, "message": "", "updater": updater}).json()


def test_update_is_requested_claimed_once_and_reported(client):
    assert client.post("/v1/service/update", headers=AUTH, json={"version": NEWER}).status_code == 409
    heartbeat(client)
    assert client.post("/v1/service/update", headers=AUTH, json={"version": __version__}).status_code == 409
    requested = client.post("/v1/service/update", headers=AUTH, json={"version": NEWER})
    assert requested.status_code == 202 and requested.json()["state"] == "requested"
    assert client.post("/v1/service/update", headers=AUTH, json={"version": NEWER}).status_code == 409
    assert heartbeat(client)["update"]["state"] == "requested"
    assert client.post("/v1/service/update/report", headers=AUTH,
                       json={"version": NEWER, "state": "failed", "message": "x"}).status_code == 409
    assert client.post("/v1/service/update/claim", headers=AUTH, json={"version": NEWER}).json()["state"] == "running"
    assert client.post("/v1/service/update/claim", headers=AUTH, json={"version": NEWER}).status_code == 409
    failed = client.post("/v1/service/update/report", headers=AUTH,
                         json={"version": NEWER, "state": "failed", "message": "Sin red"}).json()
    assert failed["state"] == "failed"
    assert client.get("/v1/library", headers=AUTH).json()["service_update"]["message"] == "Sin red"
    # A failed attempt can be retried.
    assert client.post("/v1/service/update", headers=AUTH, json={"version": NEWER}).status_code == 202


def test_update_waits_for_usb_copy_and_rejects_bad_versions(client):
    heartbeat(client, state="working")
    assert "copia USB" in client.post("/v1/service/update", headers=AUTH, json={"version": NEWER}).json()["detail"]
    assert client.post("/v1/service/update", headers=AUTH, json={"version": "../1.0.0"}).status_code == 422


def test_restarted_service_completes_and_stale_requests_fail():
    stamp = "2026-01-01T00:00:00+00:00"
    request = {"version": __version__, "state": "running", "message": "", "requested_at": stamp, "updated_at": stamp}
    assert service_update.view(request)["state"] == "complete"
    assert service_update.view({**request, "version": NEWER, "state": "requested"})["state"] == "failed"
    assert service_update.view({**request, "version": NEWER})["state"] == "failed"
    fresh = service_update.library.now()
    assert service_update.view({**request, "version": NEWER, "requested_at": fresh, "updated_at": fresh})["state"] == "running"


def package(version, files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return stream.getvalue()


def serve(version, data, checksum=None):
    sums = f"{checksum or hashlib.sha256(data).hexdigest()}  prelo-macos-{version}.zip\n".encode()
    return lambda url, limit=None: sums if url.endswith("SHA256SUMS") else data


def test_release_package_is_verified_before_unpacking(tmp_path):
    manifest = json.dumps({"id": "margen", "version": "9.9.9"})
    good = package("9.9.9", {"prelo-9.9.9/manifest.json": manifest, "prelo-9.9.9/scripts/install.py": "print()"})
    target = updater.fetch("9.9.9", tmp_path, get=serve("9.9.9", good))
    assert (target / "scripts/install.py").read_text() == "print()"
    with pytest.raises(ValueError, match="no coincide"):
        updater.fetch("9.9.9", tmp_path / "other", get=serve("9.9.9", good, "0" * 64))
    escape = package("9.9.9", {"prelo-9.9.9/manifest.json": manifest, "prelo-9.9.9/../../evil": "x"})
    with pytest.raises(ValueError, match="rutas"):
        updater.fetch("9.9.9", tmp_path / "escape", get=serve("9.9.9", escape))
    assert not (tmp_path / "evil").exists()
    other = package("9.9.9", {"prelo-9.9.9/manifest.json": json.dumps({"id": "margen", "version": "1.0.0"})})
    with pytest.raises(ValueError, match="no corresponde"):
        updater.fetch("9.9.9", tmp_path / "other-version", get=serve("9.9.9", other))
    with pytest.raises(ValueError):
        updater.fetch("9.9.9/../x", tmp_path)


def test_connector_claims_the_request_and_hands_over_or_reports(tmp_path, monkeypatch):
    from margen.native import Worker
    calls, launched = [], []
    worker = Worker({"vault": str(tmp_path), "state": str(tmp_path / "state"), "update_command": ["true"]}, tmp_path / "usb.json")
    worker.api = lambda route, body=None, binary=False: calls.append((route, body)) or ([] if route == "/v1/jobs" else {})
    monkeypatch.setattr(updater, "fetch", lambda version, folder: folder / f"prelo-{version}")
    monkeypatch.setattr(updater, "launch", lambda *args: launched.append(args))
    worker.update_service({"version": NEWER, "state": "running"})
    assert not calls
    worker.update_service({"version": NEWER, "state": "requested"})
    assert [route for route, _ in calls] == ["/v1/jobs", "/v1/service/update/claim"]
    assert launched == [(tmp_path / "usb.json", tmp_path / "updates" / f"prelo-{NEWER}", NEWER)]
    calls.clear()

    def missing(version, folder):
        raise ValueError("La release no incluye el paquete para macOS.")
    monkeypatch.setattr(updater, "fetch", missing)
    worker.update_service({"version": NEWER, "state": "requested"})
    assert calls[-1] == ("/v1/service/update/report", {"version": NEWER, "state": "failed",
                                                       "message": "La release no incluye el paquete para macOS."})
    calls.clear()
    plain = Worker({"vault": str(tmp_path), "state": str(tmp_path / "state")}, tmp_path / "usb.json")
    plain.api = worker.api
    plain.update_service({"version": NEWER, "state": "requested"})
    assert not calls and not plain.can_update()
