from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import attachments, emails, health, imports, search, settings
from app.config import get_settings
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.import_dir.mkdir(parents=True, exist_ok=True)
    settings.attachment_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="Local PST Semantic Search", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(imports.router)
app.include_router(search.router)
app.include_router(emails.router)
app.include_router(attachments.router)
app.include_router(settings.router)
