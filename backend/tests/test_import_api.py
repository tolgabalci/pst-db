from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


@pytest.fixture(autouse=True)
def disable_startup_db(monkeypatch):
    monkeypatch.setattr("app.main.init_db", lambda: None)


def test_scan_endpoint_finds_uppercase_pst(tmp_path: Path):
    (tmp_path / "Inbox.PST").write_bytes(b"pst")

    app.dependency_overrides[get_settings] = lambda: Settings(import_dir=tmp_path)
    try:
        with TestClient(app) as client:
            response = client.post("/api/imports/scan")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["files"][0]["filename"] == "Inbox.PST"


def test_get_scan_endpoint_does_not_treat_scan_as_job_id(tmp_path: Path):
    (tmp_path / "Inbox.PST").write_bytes(b"pst")

    app.dependency_overrides[get_settings] = lambda: Settings(import_dir=tmp_path)
    try:
        with TestClient(app) as client:
            response = client.get("/api/imports/scan")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["files"][0]["filename"] == "Inbox.PST"


def test_create_import_accepts_uppercase_relative_path(tmp_path: Path, monkeypatch):
    (tmp_path / "Inbox.PST").write_bytes(b"pst")
    fake_job = {
        "id": "00000000-0000-0000-0000-000000000001",
        "source_filename": "Inbox.PST",
        "status": "queued",
    }

    monkeypatch.setattr("app.api.imports.get_conn", lambda: _FakeContext(Mock()))
    monkeypatch.setattr("app.api.imports.create_import_job", lambda conn, settings, source_path: fake_job)
    app.dependency_overrides[get_settings] = lambda: Settings(import_dir=tmp_path)
    try:
        with TestClient(app) as client:
            response = client.post("/api/imports", json={"source_path": "Inbox.PST"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["source_filename"] == "Inbox.PST"


class _FakeContext:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, *_args):
        return False
