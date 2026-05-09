from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.db import get_conn
from app.services.import_runner import create_import_job, scan_import_dir

router = APIRouter(prefix="/api/imports", tags=["imports"])


class ImportCreate(BaseModel):
    source_path: str


@router.get("")
def list_imports():
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT *
            FROM import_jobs
            ORDER BY created_at DESC
            LIMIT 100
            """
        ).fetchall()


@router.post("/scan")
def scan(settings: Settings = Depends(get_settings)):
    return {"files": scan_import_dir(settings)}


@router.get("/scan")
def scan_get(settings: Settings = Depends(get_settings)):
    return scan(settings)


@router.post("")
def create_import(body: ImportCreate, settings: Settings = Depends(get_settings)):
    try:
        with get_conn() as conn:
            return create_import_job(conn, settings, body.source_path)
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
