from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.db import get_conn
from app.services.app_settings import get_cache_settings
from app.services.import_runner import create_import_job, scan_import_dir
from app.services.runtime_cache import FOLDER_LIST_CACHE, IMPORT_STATUS_CACHE, SEARCH_RESULT_CACHE

router = APIRouter(prefix="/api/imports", tags=["imports"])


class ImportCreate(BaseModel):
    source_path: str


@router.get("")
def list_imports():
    with get_conn() as conn:
        cache_settings = get_cache_settings(conn)
        cached = IMPORT_STATUS_CACHE.get(
            "list_imports",
            cache_settings.import_status_cache_entries,
            cache_settings.import_status_cache_ttl_seconds,
        )
        if cached is not None:
            return cached
        result = conn.execute(
            """
            SELECT *
            FROM import_jobs
            ORDER BY created_at DESC
            LIMIT 100
            """
        ).fetchall()
    IMPORT_STATUS_CACHE.set(
        "list_imports",
        result,
        cache_settings.import_status_cache_entries,
        cache_settings.import_status_cache_ttl_seconds,
    )
    return result


@router.post("/scan")
def scan(settings: Settings = Depends(get_settings)):
    with get_conn() as conn:
        cache_settings = get_cache_settings(conn)
    cache_key = ("scan_imports", str(settings.import_dir.resolve()))
    cached = IMPORT_STATUS_CACHE.get(
        cache_key,
        cache_settings.import_status_cache_entries,
        cache_settings.import_status_cache_ttl_seconds,
    )
    if cached is not None:
        return cached
    result = {"files": scan_import_dir(settings)}
    IMPORT_STATUS_CACHE.set(
        cache_key,
        result,
        cache_settings.import_status_cache_entries,
        cache_settings.import_status_cache_ttl_seconds,
    )
    return result


@router.get("/scan")
def scan_get(settings: Settings = Depends(get_settings)):
    return scan(settings)


@router.post("")
def create_import(body: ImportCreate, settings: Settings = Depends(get_settings)):
    try:
        with get_conn() as conn:
            job = create_import_job(conn, settings, body.source_path)
        IMPORT_STATUS_CACHE.clear()
        FOLDER_LIST_CACHE.clear()
        SEARCH_RESULT_CACHE.clear()
        return job
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{job_id}")
def get_import(job_id: UUID):
    with get_conn() as conn:
        job = conn.execute("SELECT * FROM import_jobs WHERE id = %s", (job_id,)).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Import job not found.")
        errors = conn.execute(
            """
            SELECT item_ref, stage, message, details, created_at
            FROM import_errors
            WHERE job_id = %s
            ORDER BY created_at DESC
            LIMIT 500
            """,
            (job_id,),
        ).fetchall()
        return {"job": job, "errors": errors}
