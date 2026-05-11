from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://pstdb:pstdb@localhost:5432/pstdb"
    import_dir: Path = Field(default=Path("./data/imports"))
    attachment_dir: Path = Field(default=Path("./data/attachments"))
    tika_url: str = "http://localhost:9998"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "embeddinggemma"
    embedding_dimensions: int = 768
    import_batch_size: int = 50
    worker_poll_seconds: float = 3.0
    max_attachment_text_chars: int = 200_000
    max_chunk_chars: int = 1_200
    chunk_overlap_chars: int = 150
    max_embedding_input_chars: int = 1_500


@lru_cache
def get_settings() -> Settings:
    return Settings()
