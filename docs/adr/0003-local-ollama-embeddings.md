# ADR-0003: Use local Ollama embeddings instead of external LLM APIs

## Status

Accepted

## Date

2026-05-10

## Context

Semantic search is required so users can find conceptually related emails even when exact keywords do not match. The input data can be sensitive and very large. Sending all email and attachment text to external embedding APIs would create privacy concerns and potentially high cost.

The target laptop is assumed to have at most about 8 GB of VRAM available for local model acceleration.

## Decision

Use Ollama as the local embedding host. Use `embeddinggemma` as the default model with 768-dimensional vectors.

The app stores generated embeddings in PostgreSQL via `pgvector`. Query embeddings are generated on demand and cached in bounded local memory. No chat LLM is required for V1.

## Consequences

Semantic search stays local and avoids external API cost. The same Compose stack can run import-time embedding generation and query-time embedding generation.

Local embedding speed depends on CPU/GPU availability and Ollama performance. Users who change the embedding model must re-embed indexed content if vector dimensions or embedding behavior change.
