# ADR-0005: Preserve source email data as read-only and store annotations separately

## Status

Accepted

## Date

2026-05-10

## Context

The application is a local read-only search and review tool, not an email client. It should never modify PST files or present itself as a tool for sending, replying, or managing mailbox state. Users still need local workflow features such as favorites and notes.

## Decision

Treat PST files as immutable source inputs. Imported email content and metadata are read-only after import except for repair/backfill behavior that improves imported metadata.

Store user annotations separately:

- Favorites live in `email_flags`.
- Notes live in `user_notes`.
- Notes are indexed into `search_documents` so they can participate in keyword and semantic search.

## Consequences

The original email evidence remains distinct from local reviewer annotations. This avoids confusing imported source content with user-generated notes.

Search results can still include note content, so future UI should make note-origin matches clear when match explanations become more detailed.
