# ADR-0008: Test startup, imports, search, and UI behavior with layered checks

## Status

Accepted

## Date

2026-05-10

## Context

The app has several failure-prone boundaries: Docker startup, database schema initialization, PST parsing, import continuation after bad items, semantic indexing, search ranking, and UI behavior around imports and browsing. The app must be safe to iterate on without requiring the full large PST dataset for every check.

## Decision

Use layered testing:

- Backend unit tests with `pytest` for hashing, parsing helpers, import continuation, database startup retry behavior, search SQL, note indexing, sanitization, cache behavior, and import APIs.
- Frontend tests with Vitest and React Testing Library for important UI behavior such as Imports tab filtering.
- A small-PST end-to-end script for full-stack import, keyword search, semantic search, detail lookup, notes, and favorites.
- A Compose smoke script for local service health and basic API behavior.
- A benchmark script for search latency and database/index sizing.

## Consequences

Most regressions can be caught quickly without reimporting a large PST archive. The small-PST test keeps end-to-end coverage practical.

The large real PST remains useful for final manual validation and performance checks, but it should not be the first or only test input because imports may run for hours.
