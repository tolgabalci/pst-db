# ADR-0007: Use bounded local caches with persisted cache settings

## Status

Accepted

## Date

2026-05-10

## Context

Repeated searches, folder scans, query embeddings, email detail loads, and attachment previews can be expensive or visually noisy if every UI action hits the database and services from scratch. The app is local and single-user, so a distributed cache such as Redis would add operational complexity without enough benefit in V1.

## Decision

Use bounded local caches:

- Backend in-process TTL/LRU caches for search result pages, query embeddings, folder list responses, and import status responses.
- Frontend session caches for opened email details and attachment metadata.
- Browser cache headers for attachment previews/downloads.
- Cache settings persisted in PostgreSQL through `app_settings` and configurable from the Settings tab.

Invalidate or bypass caches when settings change, imports start, notes change, or favorites change.

## Consequences

Common repeated interactions are faster without adding another service. Cache size and TTL can be tuned locally.

In-process backend caches are per-container and are cleared on service restart. Cached search failures from semantic embedding errors are not stored, so transient Ollama failures do not poison future searches.
