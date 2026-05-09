import uuid

from psycopg import Connection

from app.config import Settings
from app.services.embeddings import EmbeddingClient, vector_literal
from app.services.text import chunk_text, clean_text


def index_note(conn: Connection, settings: Settings, email_id, note: str) -> int:
    clean_note = clean_text(note).strip()
    conn.execute(
        "DELETE FROM search_documents WHERE email_id = %s AND source_type = 'note'",
        (email_id,),
    )
    if not clean_note:
        return 0

    inserted_docs: list[tuple[uuid.UUID, str]] = []
    for chunk_index, chunk in enumerate(chunk_text(clean_note, settings.max_chunk_chars, settings.chunk_overlap_chars)):
        doc_id = uuid.uuid4()
        conn.execute(
            """
            INSERT INTO search_documents (id, email_id, attachment_id, source_type, title, chunk_index, content)
            VALUES (%s, %s, NULL, 'note', 'User note', %s, %s)
            """,
            (doc_id, email_id, chunk_index, clean_text(chunk)),
        )
        inserted_docs.append((doc_id, clean_text(f"User note\n{chunk}")))

    if not inserted_docs:
        return 0

    embeddings, error = EmbeddingClient(settings).embed([content for _, content in inserted_docs])
    if error or len(embeddings) != len(inserted_docs):
        conn.execute(
            """
            UPDATE search_documents
            SET embedding_status = 'error', embedding_error = %s
            WHERE id = ANY(%s)
            """,
            (error or "Embedding count did not match note chunk count.", [doc_id for doc_id, _ in inserted_docs]),
        )
        return 0

    semantic_count = 0
    for (doc_id, _), embedding in zip(inserted_docs, embeddings, strict=True):
        conn.execute(
            """
            UPDATE search_documents
            SET embedding = %s::vector, embedding_status = 'done', embedding_error = NULL
            WHERE id = %s
            """,
            (vector_literal(embedding), doc_id),
        )
        semantic_count += 1
    return semantic_count
