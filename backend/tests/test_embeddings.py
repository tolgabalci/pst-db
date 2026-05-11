from app.config import Settings
from app.services.embeddings import EmbeddingClient


def test_embedding_client_caps_inputs_before_calling_ollama(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"embeddings": [[0.1, 0.2, 0.3]]}

    def fake_post(_url, json, timeout):
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.services.embeddings.httpx.post", fake_post)

    text = "Title " + ("verylongtoken " * 200)
    embeddings, error = EmbeddingClient(
        Settings(embedding_dimensions=3, max_embedding_input_chars=80)
    ).embed([text])

    assert error is None
    assert embeddings == [[0.1, 0.2, 0.3]]
    assert len(captured["json"]["input"][0]) <= 80
    assert captured["json"]["input"][0].endswith("verylongtoken")


def test_embedding_client_cleans_and_drops_empty_inputs(monkeypatch):
    called = False

    def fake_post(*_args, **_kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr("app.services.embeddings.httpx.post", fake_post)

    embeddings, error = EmbeddingClient(Settings()).embed(["\ud83d", " \n\t "])

    assert embeddings == []
    assert error is None
    assert not called
