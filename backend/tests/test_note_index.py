from unittest.mock import Mock
from uuid import uuid4

from app.config import Settings
from app.services.note_index import index_note


def test_index_note_replaces_note_documents_and_embeds(monkeypatch):
    conn = _RecordingConn()
    email_id = uuid4()

    class FakeEmbeddingClient:
        def __init__(self, _settings):
            pass

        def embed(self, texts):
            inputs = list(texts)
            return [[0.1, 0.2, 0.3] for _text in inputs], None

    monkeypatch.setattr("app.services.note_index.EmbeddingClient", FakeEmbeddingClient)

    count = index_note(
        conn,
        Settings(embedding_dimensions=3, max_chunk_chars=100, chunk_overlap_chars=0),
        email_id,
        "Important deployment clue",
    )

    rendered = "\n".join(statement for statement, _params in conn.statements)
    assert count == 1
    assert "DELETE FROM search_documents" in rendered
    assert "'note'" in rendered
    assert "SET embedding = %s::vector" in rendered
    assert any(
        "INSERT INTO search_documents" in statement and params and params[1] == email_id
        for statement, params in conn.statements
    )


def test_index_note_clears_documents_for_empty_note():
    conn = _RecordingConn()

    count = index_note(conn, Settings(), uuid4(), "   ")

    rendered = "\n".join(statement for statement, _params in conn.statements)
    assert count == 0
    assert "DELETE FROM search_documents" in rendered
    assert "INSERT INTO search_documents" not in rendered


def test_index_note_keeps_keyword_document_when_embedding_fails(monkeypatch):
    conn = _RecordingConn()

    class FakeEmbeddingClient:
        def __init__(self, _settings):
            pass

        def embed(self, _texts):
            return [], "embedding unavailable"

    monkeypatch.setattr("app.services.note_index.EmbeddingClient", FakeEmbeddingClient)

    count = index_note(conn, Settings(), uuid4(), "Keyword searchable note")

    rendered = "\n".join(statement for statement, _params in conn.statements)
    assert count == 0
    assert "INSERT INTO search_documents" in rendered
    assert "embedding_status = 'error'" in rendered


class _RecordingConn:
    def __init__(self):
        self.statements = []

    def execute(self, statement, params=None):
        self.statements.append((statement, params))
        return Mock(fetchone=lambda: None, fetchall=lambda: [])
