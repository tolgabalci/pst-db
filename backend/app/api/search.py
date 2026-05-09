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
