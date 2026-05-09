from fastapi import APIRouter

from app.db import get_conn
from app.services.app_settings import CacheSettings, get_cache_settings, save_cache_settings
from app.services.runtime_cache import clear_runtime_caches

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings() -> CacheSettings:
    with get_conn() as conn:
        return get_cache_settings(conn)


@router.put("")
def update_settings(body: CacheSettings) -> CacheSettings:
    with get_conn() as conn:
        saved = save_cache_settings(conn, body)
    clear_runtime_caches()
    return saved
