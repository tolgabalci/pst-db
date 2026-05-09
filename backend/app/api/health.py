from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.db import get_conn

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health(settings: Settings = Depends(get_settings)):
    with get_conn() as conn:
        conn.execute("SELECT 1").fetchone()
    return {
        "status": "ok",
        "ollama_model": settings.ollama_model,
        "embedding_dimensions": settings.embedding_dimensions,
    }

