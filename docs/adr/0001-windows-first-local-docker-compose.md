# ADR-0001: Run as a Windows-first local Docker Compose application

## Status

Accepted

## Date

2026-05-10

## Context

The app must run on a user's local Windows machine and process large Outlook PST archives without sending email content to external services. The system needs repeatable startup and shutdown scripts that bring up the web app, API, database, import worker, Tika, and embedding host together.

The target machines may use Docker Desktop or Rancher Desktop with WSL2-style Linux containers. Some users may have GPU acceleration available through WSL/NVIDIA passthrough, but the app must still run without requiring cloud infrastructure.

## Decision

Use Docker Compose as the runtime boundary. Provide PowerShell scripts for startup and shutdown:

- `scripts/up.ps1` creates required local data folders and starts Compose services.
- `scripts/down.ps1` stops services without deleting imported data.
- Compose binds published ports to `127.0.0.1` by default.
- Rancher Desktop GPU support is configured through Linux container device and WSL library mounts for Ollama.

## Consequences

This keeps setup and teardown simple for a local single-user workflow and avoids installing PostgreSQL, Tika, Ollama, and Python dependencies directly on Windows.

The deployment is intentionally not hardened for LAN or internet exposure. V1 has no login, multi-user isolation, TLS termination, or server-grade operations model.

Docker startup can overlap API and worker schema initialization. The database initialization code retries transient PostgreSQL lock conflicts and deadlocks to keep startup reliable.
