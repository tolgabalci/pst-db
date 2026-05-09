from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field


SETTINGS_KEY = "cache"


class CacheSettings(BaseModel):
    search_result_cache_entries: int = Field(default=128, ge=0, le=10_000)
    search_result_cache_ttl_seconds: int = Field(default=60, ge=0, le=86_400)
    query_embedding_cache_entries: int = Field(default=512, ge=0, le=50_000)
    query_embedding_cache_ttl_seconds: int = Field(default=3_600, ge=0, le=604_800)
    folder_list_cache_entries: int = Field(default=4, ge=0, le=1_000)
    folder_list_cache_ttl_seconds: int = Field(default=30, ge=0, le=3_600)
    import_status_cache_entries: int = Field(default=8, ge=0, le=1_000)
    import_status_cache_ttl_seconds: int = Field(default=2, ge=0, le=300)
    email_detail_cache_entries: int = Field(default=150, ge=0, le=10_000)
    attachment_metadata_cache_entries: int = Field(default=150, ge=0, le=10_000)
    attachment_preview_cache_max_age_seconds: int = Field(default=86_400, ge=0, le=2_592_000)


def get_cache_settings(conn: Connection) -> CacheSettings:
    row = conn.execute("SELECT value FROM app_settings WHERE key = %s", (SETTINGS_KEY,)).fetchone()
    if not row:
        return CacheSettings()
    value = row["value"] or {}
    if not isinstance(value, dict):
        value = {}
    return CacheSettings.model_validate(value)


def save_cache_settings(conn: Connection, settings: CacheSettings) -> CacheSettings:
    value: dict[str, Any] = settings.model_dump()
    conn.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (%s, %s::jsonb, now())
        ON CONFLICT (key)
        DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """,
        (SETTINGS_KEY, Jsonb(value)),
    )
    conn.commit()
    return settings
