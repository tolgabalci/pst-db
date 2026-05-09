from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from psycopg import Connection, errors
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

_pool: ConnectionPool | None = None
_SCHEMA_LOCK_ID = 790384231
_EXTENSIONS = ("vector", "pg_trgm", "unaccent")


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            settings.database_url,
            min_size=1,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=True,
        )
    return _pool


@contextmanager
def get_conn() -> Iterator[Connection]:
    with get_pool().connection() as conn:
        yield conn


def init_db() -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    sql = _schema_without_extensions(schema_path.read_text(encoding="utf-8"))
    with get_conn() as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_SCHEMA_LOCK_ID,))
        conn.commit()
        try:
            _create_extensions(conn)
            conn.execute(sql)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            try:
                conn.execute("SELECT pg_advisory_unlock(%s)", (_SCHEMA_LOCK_ID,))
                conn.commit()
            except Exception:
                conn.rollback()


def _create_extensions(conn: Connection) -> None:
    for extension in _EXTENSIONS:
        try:
            conn.execute(f"CREATE EXTENSION IF NOT EXISTS {extension}")
            conn.commit()
        except (errors.DuplicateObject, errors.UniqueViolation):
            conn.rollback()


def _schema_without_extensions(sql: str) -> str:
    return "\n".join(
        line
        for line in sql.splitlines()
        if not line.strip().upper().startswith("CREATE EXTENSION ")
    )
