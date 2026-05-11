# ADR-0002: Store imported mail in PostgreSQL with pgvector

## Status

Accepted

## Date

2026-05-10

## Context

The app needs to search tens of gigabytes of PST data, preserve source PST/folder occurrences, support notes and favorites, and perform both keyword and semantic search locally. It also needs a database that can run inside Docker Compose on a laptop.

The system should avoid adding separate services unless they materially improve the design.

## Decision

Use PostgreSQL 16 as the primary local data store, using:

- Normal relational tables for emails, recipients, occurrences, attachments, import jobs, errors, notes, and favorites.
- PostgreSQL full-text search and GIN indexes for keyword search.
- `pg_trgm` for text filter acceleration where useful.
- `pgvector` with HNSW indexing for embedding similarity search.
- Local filesystem storage under `data/attachments` for de-duped attachment bytes, with database rows pointing to the stored blobs.

## Consequences

PostgreSQL becomes the single durable query source for imported metadata, text, annotations, and semantic vectors. This simplifies backup and local operations compared with splitting keyword search, metadata, and vector search across multiple engines.

Very large imports still need careful indexing, query planning, and disk-space management. Changing embedding models or vector dimensions requires re-embedding and may require schema/index changes.
