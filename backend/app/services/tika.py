import mimetypes
from pathlib import Path

import httpx

from app.config import Settings


def guess_mime(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


class TikaClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def extract_text(self, path: Path, mime_type: str | None = None) -> tuple[str, str | None]:
        headers = {
            "Accept": "text/plain",
            "Content-Type": mime_type or guess_mime(path.name),
        }
        try:
            with path.open("rb") as handle:
                response = httpx.put(
                    f"{self.settings.tika_url.rstrip('/')}/tika",
                    content=handle,
                    headers=headers,
                    timeout=120,
                )
            response.raise_for_status()
            text = response.text[: self.settings.max_attachment_text_chars]
            return text, None
        except Exception as exc:  # noqa: BLE001 - persisted as import diagnostics
            return "", str(exc)

