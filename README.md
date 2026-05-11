# Local PST Semantic Search

Local, read-only PST search for large Outlook exports. The app runs on a Windows laptop with Docker Desktop or Rancher Desktop, imports PST files from a watched folder, extracts email and attachment text, stores de-duped attachments, and searches with both PostgreSQL full text and local Ollama embeddings.

## Requirements

- Windows with Docker Desktop or Rancher Desktop using WSL2-style Linux containers.
- Rancher Desktop may need to be started as Administrator before running the scripts, depending on how its Docker pipe is configured.
- Enough disk space for PostgreSQL indexes plus de-duped attachment storage.
- Optional GPU acceleration for Ollama. The default `embeddinggemma` model is intended to fit the assumed 8 GB VRAM budget.
- On Rancher Desktop with WSL2/NVIDIA, the Ollama container uses manual WSL GPU passthrough by mounting `/dev/dxg`, `/usr/lib/wsl/lib`, and `/usr/lib/wsl/drivers`.

## Run

```powershell
Copy-Item .env.example .env
.\scripts\up.ps1 -PullEmbeddingModel
```

Open `http://localhost:5173`. Copy PST files into `data\imports`, then start imports from the Import screen.

By default, Docker Compose binds every published service port to `127.0.0.1` only. This app has no authentication in V1 and is intended for local single-user use, so do not expose it directly to a LAN or the internet.

Stop services without deleting imported data:

```powershell
.\scripts\down.ps1
```

## Architecture

- `postgres`: PostgreSQL 16 with pgvector and full-text indexes.
- `api`: FastAPI service exposing search, email detail, attachments, notes, favorites, and import job APIs.
- `worker`: long-running PST importer using `libpff`/`pypff`, Apache Tika, and Ollama embeddings.
- `tika`: attachment text extraction.
- `ollama`: local embedding model host.
- `web`: React/Vite master-detail UI.

PSTs are treated as source inputs only. After import, searchable text, metadata, annotations, and de-duped attachment bytes are stored under `data\`.

Architectural decisions are recorded in [`docs/adr`](docs/adr/README.md).

The repository intentionally ignores `.env`, `data\`, `tmp\`, PST/OST/MBOX files, extracted attachment bytes, PostgreSQL files, generated frontend builds, dependency folders, and Python caches. Do not commit real Outlook exports or imported databases.

## Search

The UI exposes three modes:

- `All`: hybrid keyword plus semantic ranking.
- `Keyword`: PostgreSQL full-text search only.
- `Semantic`: embedding similarity only.

Filters include author/recipient, subject, attachment filename, date range, has attachments, and favorites.

## Operational Notes

- Imports continue past corrupt messages and unsupported attachments; job errors are persisted.
- Exact duplicate emails collapse into one canonical result. Source PST and folder occurrences are preserved.
- Notes and favorites are local annotations stored separately from imported email content.
- OCR and chat/Q&A are not included in V1.

## Development Checks

Backend unit tests:

```powershell
cd backend
python -m pytest
```

Frontend build:

```powershell
cd frontend
npm install
npm run build
```

Compose smoke check after `up.ps1`:

```powershell
.\scripts\smoke.ps1
```

Isolated small-PST end-to-end check. This starts a temporary Compose project on alternate ports, downloads a 271 KB valid PST fixture, scans it, imports it, verifies keyword/semantic/author searches, verifies email detail, and checks favorites/notes:

```powershell
.\scripts\e2e-sample-pst.ps1
```

Basic search latency benchmark:

```powershell
.\scripts\benchmark.ps1 -Query "project contract terms" -Runs 20
```
