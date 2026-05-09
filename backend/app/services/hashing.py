import hashlib
from dataclasses import dataclass

from app.services.text import normalize_for_hash


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class FingerprintAttachment:
    filename: str
    content_hash: str


def email_fingerprint(
    *,
    message_id: str | None,
    subject: str | None,
    sender_email: str | None,
    sent_at_iso: str | None,
    body_text: str | None,
    attachments: list[FingerprintAttachment],
) -> str:
    parts = [
        "message_id=" + normalize_for_hash(message_id),
        "subject=" + normalize_for_hash(subject),
        "sender=" + normalize_for_hash(sender_email),
        "sent_at=" + normalize_for_hash(sent_at_iso),
        "body=" + normalize_for_hash(body_text),
    ]
    for attachment in sorted(attachments, key=lambda item: item.content_hash):
        parts.append(f"attachment={attachment.content_hash}")
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
