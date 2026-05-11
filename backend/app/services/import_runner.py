import json
import time
import uuid
from pathlib import Path

from psycopg import errors
from psycopg import Connection

from app.config import Settings
from app.importers.pst import ParsedEmail, ParsedError, PstReader
from app.services.embeddings import EmbeddingClient, vector_literal
from app.services.hashing import FingerprintAttachment, email_fingerprint, sha256_bytes, sha256_file
from app.services.text import chunk_text, clean_text
from app.services.tika import TikaClient, guess_mime


def safe_relative_import_path(settings: Settings, source_path: str) -> Path:
    base = settings.import_dir.resolve()
    candidate = (base / source_path).resolve() if not Path(source_path).is_absolute() else Path(source_path).resolve()
    if base != candidate and base not in candidate.parents:
        raise ValueError("PST path must be inside the configured import directory.")
    if candidate.suffix.casefold() != ".pst":
        raise ValueError("Only .pst files can be imported.")
    if not candidate.exists() or not candidate.is_file():
        raise FileNotFoundError(f"PST file not found: {candidate}")
    return candidate


def attachment_storage_path(settings: Settings, content_hash: str) -> Path:
    return settings.attachment_dir / content_hash[:2] / content_hash


def create_import_job(conn: Connection, settings: Settings, source_path: str) -> dict:
    pst_path = safe_relative_import_path(settings, source_path)
    job_id = uuid.uuid4()
    existing = conn.execute(
        """
        SELECT * FROM import_jobs
        WHERE source_path = %s AND status IN ('queued', 'running')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (str(pst_path),),
    ).fetchone()
    if existing:
        return existing

    row = conn.execute(
        """
        INSERT INTO import_jobs (id, source_filename, source_path, file_size)
        VALUES (%s, %s, %s, %s)
        RETURNING *
        """,
        (job_id, pst_path.name, str(pst_path), pst_path.stat().st_size),
    ).fetchone()
    conn.commit()
    return row


def scan_import_dir(settings: Settings) -> list[dict]:
    settings.import_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict] = []
    pst_paths = [
        path
        for path in settings.import_dir.iterdir()
        if path.is_file() and path.suffix.casefold() == ".pst"
    ]
    for path in sorted(pst_paths, key=lambda item: item.name.casefold()):
        stat = path.stat()
        items.append(
            {
                "filename": path.name,
                "source_path": str(path),
                "relative_path": path.name,
                "file_size": stat.st_size,
                "modified_at": stat.st_mtime,
            }
        )
    return items


class ImportRunner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.tika = TikaClient(settings)
        self.embedder = EmbeddingClient(settings)

    def reset_interrupted_jobs(self, conn: Connection) -> None:
        conn.execute(
            """
            UPDATE import_jobs
            SET status = 'queued', started_at = NULL, last_error = 'Worker restarted before job completed.'
            WHERE status = 'running'
            """
        )
        conn.commit()

    def claim_next_job(self, conn: Connection) -> dict | None:
        row = conn.execute(
            """
            WITH next_job AS (
              SELECT id
              FROM import_jobs
              WHERE status = 'queued'
              ORDER BY created_at
              FOR UPDATE SKIP LOCKED
              LIMIT 1
            )
            UPDATE import_jobs
            SET status = 'running', started_at = now(), last_error = NULL
            FROM next_job
            WHERE import_jobs.id = next_job.id
            RETURNING import_jobs.*
            """
        ).fetchone()
        conn.commit()
        return row

    def run_job(self, conn: Connection, job: dict) -> None:
        pst_path = Path(job["source_path"])
        try:
            reader = PstReader(pst_path)
            for item in reader.iter_items():
                if isinstance(item, ParsedError):
                    self._record_error(conn, job["id"], item.item_ref, item.stage, item.message)
                    continue
                self._ingest_email_with_error_isolation(conn, job, pst_path, item)

            checksum = sha256_file(pst_path)
            conn.execute(
                "UPDATE import_jobs SET sha256 = %s, status = 'completed', finished_at = now() WHERE id = %s",
                (checksum, job["id"]),
            )
            conn.commit()
        except Exception as exc:  # noqa: BLE001 - persisted as job failure
            conn.execute(
                """
                UPDATE import_jobs
                SET status = 'failed', finished_at = now(), last_error = %s, error_count = error_count + 1
                WHERE id = %s
                """,
                (str(exc), job["id"]),
            )
            conn.commit()

    def _ingest_email_with_error_isolation(self, conn: Connection, job: dict, pst_path: Path, email: ParsedEmail) -> None:
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                self._ingest_email(conn, job, pst_path, email)
                return
            except (errors.DeadlockDetected, errors.SerializationFailure, errors.LockNotAvailable) as exc:
                conn.rollback()
                if attempt < max_attempts - 1:
                    time.sleep(0.5 * (attempt + 1))
                    continue
                self._record_error(conn, job["id"], self._email_ref(email), "email_ingest", str(exc))
                return
            except Exception as exc:  # noqa: BLE001 - isolate corrupt/unencodable messages
                conn.rollback()
                self._record_error(
                    conn,
                    job["id"],
                    self._email_ref(email),
                    "email_ingest",
                    str(exc),
                )
                return

    def _ingest_email(self, conn: Connection, job: dict, pst_path: Path, email: ParsedEmail) -> None:
        attachment_refs: list[tuple[FingerprintAttachment, uuid.UUID, str, str | None, str | None, int]] = []
        for attachment in email.attachments:
            content_hash = sha256_bytes(attachment.data)
            blob_id = self._store_attachment_blob(
                conn,
                attachment.filename,
                attachment.data,
                content_hash,
                attachment.mime_type,
            )
            attachment_refs.append(
                (
                    FingerprintAttachment(filename=attachment.filename, content_hash=content_hash),
                    blob_id,
                    attachment.filename,
                    attachment.content_id,
                    attachment.disposition,
                    attachment.ordinal,
                )
            )

        sent_at_iso = email.sent_at.isoformat() if email.sent_at else None
        content_hash = email_fingerprint(
            message_id=email.message_id,
            subject=email.subject,
            sender_email=email.sender_email,
            sent_at_iso=sent_at_iso,
            body_text=email.body_text,
            attachments=[ref[0] for ref in attachment_refs],
        )

        inserted, email_id = self._insert_or_get_email(conn, email, content_hash)
        self._insert_occurrence(conn, email_id, job["id"], pst_path, email)

        if inserted:
            self._insert_recipients(conn, email_id, email)
            self._insert_email_attachments(conn, email_id, attachment_refs)
            semantic_count = self._index_email(conn, email_id)
            conn.execute(
                """
                UPDATE import_jobs
                SET processed_count = processed_count + 1,
                    inserted_count = inserted_count + 1,
                    attachment_count = attachment_count + %s,
                    semantic_indexed_count = semantic_indexed_count + %s
                WHERE id = %s
                """,
                (len(attachment_refs), semantic_count, job["id"]),
            )
        else:
            self._repair_existing_email(conn, email_id, email, attachment_refs)
            conn.execute(
                """
                UPDATE import_jobs
                SET processed_count = processed_count + 1,
                    duplicate_count = duplicate_count + 1
                WHERE id = %s
                """,
                (job["id"],),
            )
        conn.commit()

    def _insert_or_get_email(self, conn: Connection, email: ParsedEmail, content_hash: str) -> tuple[bool, uuid.UUID]:
        email_id = uuid.uuid4()
        row = conn.execute(
            """
            INSERT INTO emails (
              id, content_hash, message_id, subject, sender_name, sender_email,
              sent_at, received_at, body_text, body_html, has_attachments
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (content_hash) DO NOTHING
            RETURNING id
            """,
            (
                email_id,
                content_hash,
                email.message_id,
                clean_text(email.subject or ""),
                clean_text(email.sender_name) or None,
                clean_text(email.sender_email) or None,
                email.sent_at,
                email.received_at,
                clean_text(email.body_text or ""),
                clean_text(email.body_html) or None,
                bool(email.attachments),
            ),
        ).fetchone()
        if row:
            return True, row["id"]
        existing = conn.execute("SELECT id FROM emails WHERE content_hash = %s", (content_hash,)).fetchone()
        return False, existing["id"]

    def _insert_occurrence(self, conn: Connection, email_id, job_id, pst_path: Path, email: ParsedEmail) -> None:
        conn.execute(
            """
            INSERT INTO email_occurrences (email_id, job_id, pst_path, folder_path, entry_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (email_id, job_id, str(pst_path), email.folder_path, email.entry_id),
        )

    def _insert_recipients(self, conn: Connection, email_id, email: ParsedEmail) -> None:
        for recipient in email.recipients:
            conn.execute(
                """
                INSERT INTO email_recipients (email_id, kind, name, email)
                VALUES (%s, %s, %s, %s)
                """,
                (email_id, clean_text(recipient.kind) or "to", clean_text(recipient.name) or None, clean_text(recipient.email) or None),
            )

    def _insert_email_attachments(self, conn: Connection, email_id, attachment_refs) -> None:
        for _, blob_id, filename, content_id, disposition, ordinal in attachment_refs:
            conn.execute(
                """
                INSERT INTO email_attachments (id, email_id, blob_id, filename, content_id, disposition, ordinal)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (uuid.uuid4(), email_id, blob_id, clean_text(filename), clean_text(content_id) or None, clean_text(disposition) or None, ordinal),
            )

    def _repair_existing_email(self, conn: Connection, email_id, email: ParsedEmail, attachment_refs) -> None:
        conn.execute(
            """
            UPDATE emails
            SET message_id = coalesce(nullif(message_id, ''), %s),
                sender_name = coalesce(nullif(sender_name, ''), %s),
                sender_email = coalesce(nullif(sender_email, ''), %s)
            WHERE id = %s
            """,
            (clean_text(email.message_id) or None, clean_text(email.sender_name) or None, clean_text(email.sender_email) or None, email_id),
        )
        has_recipients = conn.execute(
            "SELECT 1 FROM email_recipients WHERE email_id = %s LIMIT 1",
            (email_id,),
        ).fetchone()
        if not has_recipients:
            self._insert_recipients(conn, email_id, email)
        for _, blob_id, filename, content_id, disposition, ordinal in attachment_refs:
            conn.execute(
                """
                UPDATE email_attachments
                SET filename = %s,
                    content_id = coalesce(%s, content_id),
                    disposition = coalesce(%s, disposition)
                WHERE email_id = %s AND blob_id = %s AND ordinal = %s
                """,
                (clean_text(filename), clean_text(content_id) or None, clean_text(disposition) or None, email_id, blob_id, ordinal),
            )

    def _store_attachment_blob(self, conn: Connection, filename: str, data: bytes, content_hash: str, mime_type: str | None = None):
        existing = conn.execute("SELECT id FROM attachment_blobs WHERE content_hash = %s", (content_hash,)).fetchone()
        if existing:
            if mime_type:
                row = conn.execute(
                    """
                    SELECT storage_path, mime_type, extraction_status
                    FROM attachment_blobs
                    WHERE id = %s
                    """,
                    (existing["id"],),
                ).fetchone()
                if row and row["mime_type"] in (None, "", "application/octet-stream"):
                    update_fields = {"mime_type": mime_type}
                    if row["extraction_status"] == "error":
                        path = self.settings.attachment_dir / row["storage_path"]
                        extracted_text, error = self.tika.extract_text(path, mime_type)
                        conn.execute(
                            """
                            UPDATE attachment_blobs
                            SET mime_type = %s,
                                extracted_text = %s,
                                extraction_status = %s,
                                extraction_error = %s
                            WHERE id = %s
                            """,
                            (mime_type, clean_text(extracted_text), "error" if error else "done", clean_text(error) or None, existing["id"]),
                        )
                    else:
                        conn.execute("UPDATE attachment_blobs SET mime_type = %s WHERE id = %s", (update_fields["mime_type"], existing["id"]))
            return existing["id"]

        blob_id = uuid.uuid4()
        destination = attachment_storage_path(self.settings, content_hash)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            with destination.open("wb") as handle:
                handle.write(data)

        mime_type = mime_type or guess_mime(filename)
        extracted_text, error = self.tika.extract_text(destination, mime_type)
        conn.execute(
            """
            INSERT INTO attachment_blobs (
              id, content_hash, storage_path, size_bytes, mime_type,
              extracted_text, extraction_status, extraction_error
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (content_hash) DO NOTHING
            """,
            (
                blob_id,
                content_hash,
                str(destination.relative_to(self.settings.attachment_dir)),
                len(data),
                mime_type,
                clean_text(extracted_text),
                "error" if error else "done",
                clean_text(error) or None,
            ),
        )
        row = conn.execute("SELECT id FROM attachment_blobs WHERE content_hash = %s", (content_hash,)).fetchone()
        return row["id"]

    def _index_email(self, conn: Connection, email_id) -> int:
        email = conn.execute("SELECT * FROM emails WHERE id = %s", (email_id,)).fetchone()
        attachments = conn.execute(
            """
            SELECT ea.id AS attachment_id, ea.filename, ab.extracted_text
            FROM email_attachments ea
            JOIN attachment_blobs ab ON ab.id = ea.blob_id
            WHERE ea.email_id = %s
            ORDER BY ea.ordinal
            """,
            (email_id,),
        ).fetchall()

        docs: list[tuple[uuid.UUID, str, object | None, str, int, str]] = []
        header = clean_text("\n".join(
            [
                f"Subject: {email['subject'] or ''}",
                f"From: {email['sender_name'] or ''} <{email['sender_email'] or ''}>",
                f"Sent: {email['sent_at'] or ''}",
                "",
                email["body_text"] or "",
            ]
        ))
        for index, chunk in enumerate(chunk_text(header, self.settings.max_chunk_chars, self.settings.chunk_overlap_chars)):
            docs.append((uuid.uuid4(), "email", None, email["subject"] or "", index, chunk))

        for attachment in attachments:
            content = clean_text(attachment["extracted_text"] or "")
            for index, chunk in enumerate(chunk_text(content, self.settings.max_chunk_chars, self.settings.chunk_overlap_chars)):
                docs.append((uuid.uuid4(), "attachment", attachment["attachment_id"], attachment["filename"], index, chunk))
            if not content:
                docs.append((uuid.uuid4(), "attachment", attachment["attachment_id"], attachment["filename"], 0, attachment["filename"]))

        inserted_docs: list[tuple[uuid.UUID, str]] = []
        for doc_id, source_type, attachment_id, title, chunk_index, content in docs:
            conn.execute(
                """
                INSERT INTO search_documents (id, email_id, attachment_id, source_type, title, chunk_index, content)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (doc_id, email_id, attachment_id, source_type, clean_text(title), chunk_index, clean_text(content)),
            )
            inserted_docs.append((doc_id, clean_text(f"{title}\n{content}")))

        if not inserted_docs:
            return 0

        conn.commit()
        embeddings, error = self.embedder.embed([content for _, content in inserted_docs])
        if error or len(embeddings) != len(inserted_docs):
            conn.execute(
                """
                UPDATE search_documents
                SET embedding_status = 'error', embedding_error = %s
                WHERE id = ANY(%s)
                """,
                (error or "Embedding count did not match chunk count.", [doc_id for doc_id, _ in inserted_docs]),
            )
            conn.commit()
            return 0

        semantic_count = 0
        for (doc_id, _), embedding in zip(inserted_docs, embeddings, strict=True):
            conn.execute(
                """
                UPDATE search_documents
                SET embedding = %s::vector, embedding_status = 'done', embedding_error = NULL
                WHERE id = %s
                """,
                (vector_literal(embedding), doc_id),
            )
            semantic_count += 1
        conn.commit()
        return semantic_count

    def _record_error(self, conn: Connection, job_id, item_ref: str, stage: str, message: str, details=None) -> None:
        conn.execute(
            """
            INSERT INTO import_errors (job_id, item_ref, stage, message, details)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (job_id, clean_text(item_ref), clean_text(stage), clean_text(message), json.dumps(details or {}, ensure_ascii=True)),
        )
        conn.execute(
            """
            UPDATE import_jobs
            SET error_count = error_count + 1, last_error = %s
            WHERE id = %s
            """,
            (clean_text(message), job_id),
        )
        conn.commit()

    def _email_ref(self, email: ParsedEmail) -> str:
        parts = [email.folder_path, email.entry_id]
        if email.subject:
            parts.append(email.subject[:120])
        return " | ".join(clean_text(part) for part in parts if part)
