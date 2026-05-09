from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.db import get_conn
from app.services.note_index import index_note
from app.services.sanitize import sanitize_html
from app.services.text import clean_text

router = APIRouter(prefix="/api/emails", tags=["emails"])


class FavoritePatch(BaseModel):
    is_favorite: bool


class NoteUpdate(BaseModel):
    note: str


@router.get("/{email_id}")
def get_email(email_id: UUID):
    with get_conn() as conn:
        email = conn.execute(
            """
            SELECT e.*, coalesce(f.is_favorite, false) AS is_favorite, coalesce(n.note, '') AS note
            FROM emails e
            LEFT JOIN email_flags f ON f.email_id = e.id
            LEFT JOIN user_notes n ON n.email_id = e.id
            WHERE e.id = %s
            """,
            (email_id,),
        ).fetchone()
        if not email:
            raise HTTPException(status_code=404, detail="Email not found.")

        recipients = conn.execute(
            """
            SELECT kind, name, email
            FROM email_recipients
            WHERE email_id = %s
            ORDER BY id
            """,
            (email_id,),
        ).fetchall()
        occurrences = conn.execute(
            """
            SELECT pst_path, folder_path, entry_id, imported_at
            FROM email_occurrences
            WHERE email_id = %s
            ORDER BY imported_at
            """,
            (email_id,),
        ).fetchall()
        return {
            "id": str(email["id"]),
            "message_id": email["message_id"],
            "subject": email["subject"],
            "sender_name": email["sender_name"],
            "sender_email": email["sender_email"],
            "sent_at": email["sent_at"],
            "received_at": email["received_at"],
            "body_text": email["body_text"],
            "body_html": sanitize_html(email["body_html"]),
            "has_attachments": email["has_attachments"],
            "is_favorite": email["is_favorite"],
            "note": email["note"],
            "recipients": recipients,
            "occurrences": occurrences,
        }


@router.get("/{email_id}/attachments")
def get_attachments(email_id: UUID):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT ea.id, ea.filename, ea.content_id, ea.disposition, ea.ordinal,
                   ab.content_hash, ab.size_bytes, ab.mime_type,
                   ab.extraction_status, ab.extraction_error,
                   length(coalesce(ab.extracted_text, '')) AS extracted_text_length
            FROM email_attachments ea
            JOIN attachment_blobs ab ON ab.id = ea.blob_id
            WHERE ea.email_id = %s
            ORDER BY ea.ordinal
            """,
            (email_id,),
        ).fetchall()
    return [
        {
            "id": str(row["id"]),
            "filename": row["filename"],
            "content_id": row["content_id"],
            "disposition": row["disposition"],
            "ordinal": row["ordinal"],
            "content_hash": row["content_hash"],
            "size_bytes": row["size_bytes"],
            "mime_type": row["mime_type"],
            "extraction_status": row["extraction_status"],
            "extraction_error": row["extraction_error"],
            "extracted_text_length": row["extracted_text_length"],
        }
        for row in rows
    ]


@router.patch("/{email_id}/favorite")
def set_favorite(email_id: UUID, body: FavoritePatch):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO email_flags (email_id, is_favorite, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (email_id)
            DO UPDATE SET is_favorite = EXCLUDED.is_favorite, updated_at = now()
            """,
            (email_id, body.is_favorite),
        )
        conn.commit()
    return {"email_id": str(email_id), "is_favorite": body.is_favorite}


@router.put("/{email_id}/note")
def set_note(email_id: UUID, body: NoteUpdate, settings: Settings = Depends(get_settings)):
    note = clean_text(body.note)
    with get_conn() as conn:
        existing = conn.execute("SELECT 1 FROM emails WHERE id = %s", (email_id,)).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Email not found.")
        conn.execute(
            """
            INSERT INTO user_notes (email_id, note, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (email_id)
            DO UPDATE SET note = EXCLUDED.note, updated_at = now()
            """,
            (email_id, note),
        )
        semantic_count = index_note(conn, settings, email_id, note)
        conn.commit()
    return {"email_id": str(email_id), "note": note, "semantic_indexed_count": semantic_count}
