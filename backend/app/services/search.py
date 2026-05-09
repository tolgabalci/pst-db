from dataclasses import dataclass
from datetime import datetime
from typing import Any

from psycopg import Connection

from app.config import Settings
from app.services.embeddings import EmbeddingClient, vector_literal

MIN_SEMANTIC_SCORE = 0.24
MIN_HYBRID_SEMANTIC_SCORE = 0.52


@dataclass
class SearchRequest:
    q: str = ""
    mode: str = "all"
    author: str | None = None
    recipient: str | None = None
    subject: str | None = None
    attachment_filename: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    has_attachments: bool | None = None
    favorite: bool | None = None
    limit: int = 50
    offset: int = 0


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, 200))


def _min_semantic_score(mode: str) -> float:
    if mode == "all":
        return MIN_HYBRID_SEMANTIC_SCORE
    return MIN_SEMANTIC_SCORE


class SearchService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.embedder = EmbeddingClient(settings)

    def search(self, conn: Connection, request: SearchRequest) -> dict[str, Any]:
        mode = request.mode if request.mode in {"all", "keyword", "semantic"} else "all"
        query = (request.q or "").strip()
        vector = None
        semantic_error = None
        if query and mode in {"all", "semantic"}:
            embeddings, semantic_error = self.embedder.embed([query])
            if embeddings:
                vector = vector_literal(embeddings[0])

        params: dict[str, Any] = {
            "query": query,
            "limit": _clamp_limit(request.limit),
            "offset": max(0, request.offset),
            "vector": vector,
            "min_semantic_score": _min_semantic_score(mode),
        }
        filters = self._filters(request, params)

        rows = self._run_search(conn, query, mode, filters, params, vector is not None)
        email_ids = [row["id"] for row in rows]
        snippets = self._snippets(conn, email_ids, query, vector)
        attachments = self._attachment_summaries(conn, email_ids)
        total = self._count(conn, query, mode, filters, params, vector is not None)

        results = []
        for row in rows:
            email_id = row["id"]
            results.append(
                {
                    "id": str(email_id),
                    "subject": row["subject"],
                    "sender_name": row["sender_name"],
                    "sender_email": row["sender_email"],
                    "sent_at": row["sent_at"],
                    "received_at": row["received_at"],
                    "has_attachments": row["has_attachments"],
                    "is_favorite": row["is_favorite"],
                    "keyword_score": float(row["keyword_score"] or 0),
                    "semantic_score": float(row["semantic_score"] or 0),
                    "score": float(row["score"] or 0),
                    "snippet": snippets.get(email_id, ""),
                    "attachments": attachments.get(email_id, []),
                    "match_reasons": self._match_reasons(row),
                }
            )
        return {"results": results, "total": total, "semantic_error": semantic_error}

    def _filters(self, request: SearchRequest, params: dict[str, Any]) -> str:
        clauses = ["TRUE"]
        if request.author:
            params["author"] = f"%{request.author.casefold()}%"
            clauses.append(
                """
                (
                  lower(coalesce(e.sender_email, '')) LIKE %(author)s
                  OR lower(coalesce(e.sender_name, '')) LIKE %(author)s
                )
                """
            )
        if request.recipient:
            params["recipient"] = f"%{request.recipient.casefold()}%"
            clauses.append(
                """
                EXISTS (
                  SELECT 1 FROM email_recipients er
                  WHERE er.email_id = e.id
                    AND er.kind IN ('to', 'cc', 'bcc')
                    AND (
                      lower(coalesce(er.email, '')) LIKE %(recipient)s
                      OR lower(coalesce(er.name, '')) LIKE %(recipient)s
                    )
                )
                """
            )
        if request.subject:
            params["subject"] = f"%{request.subject}%"
            clauses.append("e.subject ILIKE %(subject)s")
        if request.attachment_filename:
            params["attachment_filename"] = f"%{request.attachment_filename}%"
            clauses.append(
                """
                EXISTS (
                  SELECT 1 FROM email_attachments ea
                  WHERE ea.email_id = e.id AND ea.filename ILIKE %(attachment_filename)s
                )
                """
            )
        if request.date_from:
            params["date_from"] = request.date_from
            clauses.append("coalesce(e.sent_at, e.received_at) >= %(date_from)s")
        if request.date_to:
            params["date_to"] = request.date_to
            clauses.append("coalesce(e.sent_at, e.received_at) <= %(date_to)s")
        if request.has_attachments is not None:
            params["has_attachments"] = request.has_attachments
            clauses.append("e.has_attachments = %(has_attachments)s")
        if request.favorite is not None:
            params["favorite"] = request.favorite
            clauses.append("coalesce(f.is_favorite, false) = %(favorite)s")
        return " AND ".join(f"({clause})" for clause in clauses)

    def _run_search(
        self,
        conn: Connection,
        query: str,
        mode: str,
        filters: str,
        params: dict[str, Any],
        has_vector: bool,
    ) -> list[dict]:
        sql = self._search_sql(query, mode, filters, has_vector, count=False)
        return list(conn.execute(sql, params).fetchall())

    def _count(self, conn: Connection, query: str, mode: str, filters: str, params: dict[str, Any], has_vector: bool) -> int:
        sql = self._search_sql(query, mode, filters, has_vector, count=True)
        row = conn.execute(sql, params).fetchone()
        return int(row["total"] if row else 0)

    def _search_sql(self, query: str, mode: str, filters: str, has_vector: bool, count: bool) -> str:
        keyword_cte = "SELECT NULL::uuid AS email_id, 0.0::float AS keyword_score WHERE FALSE"
        semantic_cte = "SELECT NULL::uuid AS email_id, 0.0::float AS semantic_score WHERE FALSE"
        where_match = "TRUE"
        if query and mode in {"all", "keyword"}:
            keyword_cte = """
              SELECT sd.email_id,
                     max(ts_rank_cd(sd.weighted_tsv, websearch_to_tsquery('english', %(query)s)))::float AS keyword_score
              FROM search_documents sd
              JOIN filtered f ON f.id = sd.email_id
              WHERE sd.weighted_tsv @@ websearch_to_tsquery('english', %(query)s)
              GROUP BY sd.email_id
            """
        if query and mode in {"all", "semantic"} and has_vector:
            semantic_cte = """
              SELECT nearest.email_id, max(nearest.semantic_score)::float AS semantic_score
              FROM (
                SELECT sd.email_id, (1 - (sd.embedding <=> %(vector)s::vector))::float AS semantic_score
                FROM search_documents sd
                JOIN filtered f ON f.id = sd.email_id
                WHERE sd.embedding IS NOT NULL
                  AND (1 - (sd.embedding <=> %(vector)s::vector)) >= %(min_semantic_score)s
                ORDER BY sd.embedding <=> %(vector)s::vector
                LIMIT 800
              ) nearest
              GROUP BY nearest.email_id
            """
        if query:
            if mode == "keyword":
                where_match = "k.email_id IS NOT NULL"
            elif mode == "semantic":
                where_match = "s.email_id IS NOT NULL"
            else:
                where_match = "(k.email_id IS NOT NULL OR s.email_id IS NOT NULL)"

        select = "count(*) AS total" if count else """
          e.id, e.subject, e.sender_name, e.sender_email, e.sent_at, e.received_at, e.has_attachments,
          coalesce(flg.is_favorite, false) AS is_favorite,
          coalesce(k.keyword_score, 0) AS keyword_score,
          coalesce(s.semantic_score, 0) AS semantic_score,
          (coalesce(k.keyword_score, 0) * 0.60 + coalesce(s.semantic_score, 0) * 0.40) AS score
        """
        order_limit = "" if count else """
          ORDER BY score DESC, coalesce(e.sent_at, e.received_at) DESC NULLS LAST, e.created_at DESC
          LIMIT %(limit)s OFFSET %(offset)s
        """

        return f"""
          WITH filtered AS (
            SELECT e.id
            FROM emails e
            LEFT JOIN email_flags f ON f.email_id = e.id
            WHERE {filters}
          ),
          keyword AS ({keyword_cte}),
          semantic AS ({semantic_cte}),
          matched AS (
            SELECT f.id, k.keyword_score, s.semantic_score
            FROM filtered f
            LEFT JOIN keyword k ON k.email_id = f.id
            LEFT JOIN semantic s ON s.email_id = f.id
            WHERE {where_match}
          )
          SELECT {select}
          FROM matched m
          JOIN emails e ON e.id = m.id
          LEFT JOIN email_flags flg ON flg.email_id = e.id
          LEFT JOIN keyword k ON k.email_id = e.id
          LEFT JOIN semantic s ON s.email_id = e.id
          {order_limit}
        """

    def _snippets(self, conn: Connection, email_ids: list, query: str, vector: str | None) -> dict:
        if not email_ids:
            return {}
        if query:
            rows = conn.execute(
                """
                SELECT DISTINCT ON (sd.email_id)
                  sd.email_id,
                  ts_headline(
                    'english',
                    sd.content,
                    websearch_to_tsquery('english', %(query)s),
                    'StartSel=<mark>, StopSel=</mark>, MaxWords=36, MinWords=12'
                  ) AS snippet
                FROM search_documents sd
                WHERE sd.email_id = ANY(%(email_ids)s)
                  AND sd.weighted_tsv @@ websearch_to_tsquery('english', %(query)s)
                ORDER BY sd.email_id, ts_rank_cd(sd.weighted_tsv, websearch_to_tsquery('english', %(query)s)) DESC
                """,
                {"email_ids": email_ids, "query": query},
            ).fetchall()
            snippets = {row["email_id"]: row["snippet"] for row in rows}
            missing = [email_id for email_id in email_ids if email_id not in snippets]
        else:
            snippets = {}
            missing = email_ids

        if missing:
            rows = conn.execute(
                """
                SELECT DISTINCT ON (email_id) email_id, left(content, 320) AS snippet
                FROM search_documents
                WHERE email_id = ANY(%s)
                ORDER BY email_id, source_type, chunk_index
                """,
                (missing,),
            ).fetchall()
            snippets.update({row["email_id"]: row["snippet"] for row in rows})
        return snippets

    def _attachment_summaries(self, conn: Connection, email_ids: list) -> dict:
        if not email_ids:
            return {}
        rows = conn.execute(
            """
            SELECT ea.email_id, ea.id, ea.filename, ab.mime_type, ab.size_bytes
            FROM email_attachments ea
            JOIN attachment_blobs ab ON ab.id = ea.blob_id
            WHERE ea.email_id = ANY(%s)
            ORDER BY ea.email_id, ea.ordinal
            """,
            (email_ids,),
        ).fetchall()
        result: dict = {}
        for row in rows:
            result.setdefault(row["email_id"], []).append(
                {
                    "id": str(row["id"]),
                    "filename": row["filename"],
                    "mime_type": row["mime_type"],
                    "size_bytes": row["size_bytes"],
                }
            )
        return result

    def _match_reasons(self, row: dict) -> list[str]:
        reasons = []
        if row["keyword_score"]:
            reasons.append("keyword")
        if row["semantic_score"]:
            reasons.append("semantic")
        if row["is_favorite"]:
            reasons.append("favorite")
        return reasons
