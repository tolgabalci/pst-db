from collections.abc import Iterable

import httpx

from app.config import Settings
from app.services.text import clean_text


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"


class EmbeddingClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def embed(self, texts: Iterable[str]) -> tuple[list[list[float]], str | None]:
        inputs = [input_text for text in texts if (input_text := self._prepare_input(text))]
        if not inputs:
            return [], None

        try:
            response = httpx.post(
                f"{self.settings.ollama_url.rstrip('/')}/api/embed",
                json={"model": self.settings.ollama_model, "input": inputs},
                timeout=300,
            )
            if response.status_code == 404:
                return self._embed_legacy(inputs)
            response.raise_for_status()
            payload = response.json()
            embeddings = payload.get("embeddings") or []
            return self._validate(embeddings), None
        except Exception as exc:  # noqa: BLE001 - surfaced in import status
            return [], str(exc)

    def _embed_legacy(self, inputs: list[str]) -> tuple[list[list[float]], str | None]:
        embeddings: list[list[float]] = []
        for text in inputs:
            response = httpx.post(
                f"{self.settings.ollama_url.rstrip('/')}/api/embeddings",
                json={"model": self.settings.ollama_model, "prompt": text},
                timeout=300,
            )
            response.raise_for_status()
            embedding = response.json().get("embedding") or []
            embeddings.append(embedding)
        return self._validate(embeddings), None

    def _validate(self, embeddings: list[list[float]]) -> list[list[float]]:
        for embedding in embeddings:
            if len(embedding) != self.settings.embedding_dimensions:
                raise ValueError(
                    f"Embedding model returned {len(embedding)} dimensions; "
                    f"expected {self.settings.embedding_dimensions}."
                )
        return embeddings

    def _prepare_input(self, text: str) -> str:
        normalized = " ".join(clean_text(text).split())
        if not normalized:
            return ""
        max_chars = self.settings.max_embedding_input_chars
        if max_chars <= 0 or len(normalized) <= max_chars:
            return normalized

        trimmed = normalized[:max_chars].rstrip()
        boundary = trimmed.rfind(" ", int(max_chars * 0.75))
        if boundary > 0:
            trimmed = trimmed[:boundary].rstrip()
        return trimmed or normalized[:max_chars]
