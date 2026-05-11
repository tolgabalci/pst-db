# ADR-0004: Import PST files through a resumable worker pipeline

## Status

Accepted

## Date

2026-05-10

## Context

Individual PST files may be very large, and combined local archives may exceed 50 GB. The UI should remain responsive while imports run. Imports need to continue past corrupt messages, unsupported attachments, and extraction failures.

Users copy PST files into a watched import folder and start imports from the UI.

## Decision

Use a long-running worker service for imports. The worker:

- Reads queued import jobs from PostgreSQL.
- Streams PST items with `libpff`/`pypff`.
- Extracts attachment text with Apache Tika.
- Stores attachment blobs by content hash.
- Chunks email, attachment, and note text for full-text and semantic indexing.
- Records item-level import errors and continues where possible.
- Retries transient database deadlocks and serialization failures during import.

The UI scans the watched folder and starts import jobs through API endpoints.

## Consequences

Long imports do not block the web API or UI. Failures are visible as import diagnostics without stopping the entire job.

PST parsing remains dependent on `libpff`/`pypff` behavior. Some corrupt messages can only be skipped, not repaired. Full resumability is bounded by what the database records for processed and inserted items.
