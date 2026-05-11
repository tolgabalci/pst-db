# ADR-0006: Provide hybrid search through a master-detail web UI

## Status

Accepted

## Date

2026-05-10

## Context

The primary workflow is quickly finding emails and scanning through matches. Users need structured filters, keyword search, semantic search, attachment inspection, notes, and favorites. The app should be efficient for repeated review, not a marketing page.

## Decision

Use a React/Vite frontend with a master-detail search layout:

- Left panel: query, search mode, filters, folder selection, result list, pagination, keyboard navigation.
- Right panel: selected email detail, recipients, source folders, attachments, notes, and sanitized body preview.
- Search modes: `All`, `Keyword`, and `Semantic`.
- Default mode: `All`, combining full-text and semantic matching.

The API exposes read-only endpoints for search, email detail, attachments, imports, notes, favorites, and settings.

## Consequences

The user can search and browse without switching pages or opening each result manually. The UI is optimized for scanning and local review workflows.

Hybrid ranking is intentionally simple in V1: the displayed score combines keyword and semantic scores. Future ranking work can add better explainability, recency weighting, and match highlighting by source.
