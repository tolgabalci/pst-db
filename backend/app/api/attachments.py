from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.config import Settings, get_settings
from app.db import get_conn

router = APIRouter(prefix="/api/attachments", tags=["attachments"])


def _attachment_file(attachment_id: UUID, settings: Settings):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT ea.filename, ab.storage_path, ab.mime_type
            FROM email_attachments ea
            JOIN attachment_blobs ab ON ab.id = ea.blob_id
            WHERE ea.id = %s
            """,
            (attachment_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Attachment not found.")
    path = (settings.attachment_dir / row["storage_path"]).resolve()
    base = settings.attachment_dir.resolve()
    if base != path and base not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid attachment path.")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Attachment file missing from local store.")
    return row, path


@router.get("/{attachment_id}/preview")
def preview_attachment(attachment_id: UUID, settings: Settings = Depends(get_settings)):
    row, path = _attachment_file(attachment_id, settings)
    return FileResponse(
        path,
        media_type=row["mime_type"] or "application/octet-stream",
        filename=row["filename"],
        content_disposition_type="inline",
    )


@router.get("/{attachment_id}/download")
def download_attachment(attachment_id: UUID, settings: Settings = Depends(get_settings)):
    row, path = _attachment_file(attachment_id, settings)
    return FileResponse(
        path,
        media_type=row["mime_type"] or "application/octet-stream",
        filename=row["filename"],
        content_disposition_type="attachment",
    )
