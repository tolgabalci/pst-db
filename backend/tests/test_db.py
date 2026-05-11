from psycopg import errors

from app import db
from app.db import _schema_without_extensions


def test_schema_without_extensions_removes_extension_statements():
    sql = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS example (id integer);
"""

    stripped = _schema_without_extensions(sql)

    assert "CREATE EXTENSION" not in stripped
    assert "CREATE TABLE IF NOT EXISTS example" in stripped


def test_init_db_retries_transient_deadlock(monkeypatch):
    calls = 0

    def fake_init_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise errors.DeadlockDetected("deadlock")

    monkeypatch.setattr(db, "_init_db_once", fake_init_once)
    monkeypatch.setattr(db.time, "sleep", lambda _seconds: None)

    db.init_db()

    assert calls == 2
