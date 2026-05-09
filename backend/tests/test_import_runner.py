from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

from psycopg import errors

from app.config import Settings
from app.importers.pst import ParsedEmail, ParsedRecipient
from app.services.hashing import FingerprintAttachment
from app.services.import_runner import ImportRunner


def test_run_job_opens_pst_before_source_sha256(monkeypatch, tmp_path: Path):
    pst = tmp_path / "Archive.PST"
    pst.write_bytes(b"pst")
    calls: list[str] = []
    conn = _FakeConn()

    class FakeReader:
        def __init__(self, path):
            calls.append(f"reader:{Path(path).name}")

        def iter_items(self):
            calls.append("iter")
            return iter(())

    monkeypatch.setattr("app.services.import_runner.PstReader", FakeReader)
    monkeypatch.setattr("app.services.import_runner.sha256_file", lambda path: calls.append("sha256") or "abc")

    ImportRunner(Settings(import_dir=tmp_path, attachment_dir=tmp_path / "attachments")).run_job(
        conn,
        {"id": "job", "source_path": str(pst)},
    )

    assert calls == ["reader:Archive.PST", "iter", "sha256"]
    assert conn.commits


def test_repair_existing_email_updates_duplicate_attachment_metadata(tmp_path: Path):
    runner = ImportRunner(Settings(import_dir=tmp_path, attachment_dir=tmp_path / "attachments"))
    conn = _RecordingConn()
    email_id = uuid4()
    blob_id = uuid4()
    email = ParsedEmail(
        entry_id="entry",
        folder_path="Root/Inbox",
        message_id="<message@example.com>",
        subject="Subject",
        sender_name="Sender",
        sender_email="sender@example.com",
        sent_at=None,
        received_at=None,
        body_text="Body",
        body_html=None,
    )
    attachment_refs = [
        (
            FingerprintAttachment(filename="Quarterly Report.PDF", content_hash="hash"),
            blob_id,
            "Quarterly Report.PDF",
            "cid-123",
            "1",
            0,
        )
    ]

    runner._repair_existing_email(conn, email_id, email, attachment_refs)

    rendered = "\n".join(statement for statement, _params in conn.statements)
    assert "UPDATE emails" in rendered
    assert "UPDATE email_attachments" in rendered
    assert any(params[0] == "Quarterly Report.PDF" for _statement, params in conn.statements if params)


def test_repair_existing_email_backfills_missing_recipients(tmp_path: Path):
    runner = ImportRunner(Settings(import_dir=tmp_path, attachment_dir=tmp_path / "attachments"))
    conn = _RecordingConn()
    email_id = uuid4()
    email = ParsedEmail(
        entry_id="entry",
        folder_path="Root/Inbox",
        message_id="<message@example.com>",
        subject="Subject",
        sender_name="Sender",
        sender_email="sender@example.com",
        sent_at=None,
        received_at=None,
        body_text="Body",
        body_html=None,
        recipients=[ParsedRecipient(kind="to", name="Recipient Name", email="recipient@example.com")],
    )

    runner._repair_existing_email(conn, email_id, email, [])

    recipient_inserts = [
        params
        for statement, params in conn.statements
        if "INSERT INTO email_recipients" in statement
    ]
    assert recipient_inserts == [(email_id, "to", "Recipient Name", "recipient@example.com")]


def test_run_job_records_ingest_error_and_continues(monkeypatch, tmp_path: Path):
    pst = tmp_path / "Archive.PST"
    pst.write_bytes(b"pst")
    good_email = ParsedEmail(
        entry_id="good",
        folder_path="Root/Inbox",
        message_id=None,
        subject="Good",
        sender_name=None,
        sender_email=None,
        sent_at=None,
        received_at=None,
        body_text="Body",
        body_html=None,
    )
    bad_email = ParsedEmail(
        entry_id="bad",
        folder_path="Root/Inbox",
        message_id=None,
        subject="Bad",
        sender_name=None,
        sender_email=None,
        sent_at=None,
        received_at=None,
        body_text="Body",
        body_html=None,
    )
    conn = _RecordingConn()
    seen = []

    class FakeReader:
        def __init__(self, _path):
            pass

        def iter_items(self):
            return iter([bad_email, good_email])

    def fake_ingest(_conn, _job, _path, email):
        seen.append(email.entry_id)
        if email.entry_id == "bad":
            raise UnicodeEncodeError("utf-8", "\ud83d", 0, 1, "surrogates not allowed")

    monkeypatch.setattr("app.services.import_runner.PstReader", FakeReader)
    monkeypatch.setattr("app.services.import_runner.sha256_file", lambda _path: "abc")
    runner = ImportRunner(Settings(import_dir=tmp_path, attachment_dir=tmp_path / "attachments"))
    monkeypatch.setattr(runner, "_ingest_email", fake_ingest)

    runner.run_job(conn, {"id": "job", "source_path": str(pst)})

    assert seen == ["bad", "good"]
    rendered = "\n".join(statement for statement, _params in conn.statements)
    assert "INSERT INTO import_errors" in rendered
    assert "status = 'completed'" in rendered
    assert "status = 'failed'" not in rendered
    assert conn.rollbacks == 1


def test_run_job_retries_transient_deadlock(monkeypatch, tmp_path: Path):
    pst = tmp_path / "Archive.PST"
    pst.write_bytes(b"pst")
    email = ParsedEmail(
        entry_id="deadlock-then-ok",
        folder_path="Root/Inbox",
        message_id=None,
        subject="Retry",
        sender_name=None,
        sender_email=None,
        sent_at=None,
        received_at=None,
        body_text="Body",
        body_html=None,
    )
    conn = _RecordingConn()
    attempts = 0

    class FakeReader:
        def __init__(self, _path):
            pass

        def iter_items(self):
            return iter([email])

    def fake_ingest(_conn, _job, _path, _email):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise errors.DeadlockDetected("deadlock detected")

    monkeypatch.setattr("app.services.import_runner.PstReader", FakeReader)
    monkeypatch.setattr("app.services.import_runner.sha256_file", lambda _path: "abc")
    monkeypatch.setattr("app.services.import_runner.time.sleep", lambda _seconds: None)
    runner = ImportRunner(Settings(import_dir=tmp_path, attachment_dir=tmp_path / "attachments"))
    monkeypatch.setattr(runner, "_ingest_email", fake_ingest)

    runner.run_job(conn, {"id": "job", "source_path": str(pst)})

    rendered = "\n".join(statement for statement, _params in conn.statements)
    assert attempts == 2
    assert "INSERT INTO import_errors" not in rendered
    assert "status = 'completed'" in rendered
    assert conn.rollbacks == 1


class _FakeConn:
    def __init__(self):
        self.commits = 0

    def execute(self, *_args, **_kwargs):
        return Mock(fetchone=lambda: None, fetchall=lambda: [])

    def commit(self):
        self.commits += 1


class _RecordingConn:
    def __init__(self):
        self.statements = []
        self.rollbacks = 0

    def execute(self, statement, params=None):
        self.statements.append((statement, params))
        return Mock(fetchone=lambda: None, fetchall=lambda: [])

    def commit(self):
        pass

    def rollback(self):
        self.rollbacks += 1
