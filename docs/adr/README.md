# Architecture Decision Records

This directory records architectural decisions for Local PST Semantic Search.

## Format

Each ADR uses:

- `Status`: Proposed, Accepted, Superseded, or Deprecated.
- `Context`: The forces and constraints that shaped the decision.
- `Decision`: The choice we made.
- `Consequences`: Tradeoffs, follow-up work, and risks.

## Index

- [ADR-0001: Run as a Windows-first local Docker Compose application](0001-windows-first-local-docker-compose.md)
- [ADR-0002: Store imported mail in PostgreSQL with pgvector](0002-postgresql-pgvector-storage.md)
- [ADR-0003: Use local Ollama embeddings instead of external LLM APIs](0003-local-ollama-embeddings.md)
- [ADR-0004: Import PST files through a resumable worker pipeline](0004-resumable-pst-import-pipeline.md)
- [ADR-0005: Preserve source email data as read-only and store annotations separately](0005-read-only-source-data-separate-annotations.md)
- [ADR-0006: Provide hybrid search through a master-detail web UI](0006-hybrid-search-master-detail-ui.md)
- [ADR-0007: Use bounded local caches with persisted cache settings](0007-configurable-local-caching.md)
- [ADR-0008: Test startup, imports, search, and UI behavior with layered checks](0008-layered-test-strategy.md)
