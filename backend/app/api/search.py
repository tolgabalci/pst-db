from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.config import Settings, get_settings
from app.db import get_conn
from app.services.search import SearchRequest, SearchService

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("")
def search(
    q: str = "",
    mode: str = Query("all", pattern="^(all|keyword|semantic)$"),
    author: str | None = None,
    recipient: str | None = None,
    folders: list[str] | None = Query(default=None),
    subject: str | None = None,
    attachment_filename: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    has_attachments: bool | None = None,
    favorite: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    settings: Settings = Depends(get_settings),
):
    request = SearchRequest(
        q=q,
        mode=mode,
        author=author,
        recipient=recipient,
        folders=folders,
        subject=subject,
        attachment_filename=attachment_filename,
        date_from=date_from,
        date_to=date_to,
        has_attachments=has_attachments,
        favorite=favorite,
        limit=limit,
        offset=offset,
    )
    service = SearchService(settings)
    with get_conn() as conn:
        return service.search(conn, request)


@router.get("/folders")
def search_folders():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
              coalesce(folder_path, pst_path) AS folder_path,
              count(DISTINCT email_id) AS email_count
            FROM email_occurrences
            GROUP BY coalesce(folder_path, pst_path)
            ORDER BY lower(coalesce(folder_path, pst_path))
            """
        ).fetchall()
    return [
        {
            "folder_path": row["folder_path"],
            "email_count": row["email_count"],
        }
        for row in rows
    ]
