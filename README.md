# ProjectPilot 

> Multi-agent AI project generator — describe your app, get a complete codebase.

## What's new in v4

| Feature | Detail |
|---|---|
| ⚡ Parallel code generation | 5 files generated concurrently — 3–4× faster |
| 🤔 Clarify endpoint | One smart question before the pipeline if prompt is vague |
| 🧪 TestGenAgent | Auto-generates pytest tests from blueprint routes |
| 🔍 Blueprint reflection | Verifies generated routes match the plan |
| 🔄 Regenerate file | Fix one file without full re-generation |
| 🚫 Job cancellation | Cancel queued/running jobs at any time |
| 📂 Live file tree | See files appear during generation (`GET /files/:id`) |
| 🧹 Auto cleanup | Old ZIPs deleted after 24h (configurable) |
| 📊 Structured JSON logging | Every LLM call logged with `duration_ms`, `job_id`, `agent` |
| 🔁 LLM retry + backoff | Up to 3 retries on timeout with exponential backoff |
| 🏗️ Tech stack selector | FastAPI/Flask, Streamlit/React, SQLite/PostgreSQL |
| 🔗 Singleton LLM client | One `httpx.Client` for all calls — no reconnect overhead |
| 🧬 Parallel debug fixes | Syntax errors fixed concurrently across files |
| 🚦 GitHub Actions CI | Runs full test suite on every push |

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Streamlit Frontend (8501)              │
└────────────────────────┬────────────────────────────┘
                         │ REST API
                         ▼
┌─────────────────────────────────────────────────────┐
│              FastAPI Backend (8000)                 │
│  POST /clarify           POST /generate-project     │
│  POST /cancel/:id        POST /regenerate-file      │
│  GET  /files/:id         GET  /validate/:id         │
│  GET  /status/:id        GET  /download/:id         │
│  GET  /health            GET  /jobs                 │
└──────┬──────────────────────────────┬───────────────┘
       │ Background Thread            │
       ▼                              ▼
┌─────────────────┐       ┌─────────────────────────┐
│  Agent Pipeline │       │  ChromaDB               │
│                 │       │  ● jobs                 │
│  1. Require     │       │  ● generation_logs      │
│  2. Planner     │       │  ● requirements         │
│  3. Code  (║)   │       │  ● blueprints           │
│  4. TestGen     │       └─────────────────────────┘
│  5. Debug (║)   │
│  6. Docs        │       ┌─────────────────────────┐
│  7. ZIP         │       │  Cleanup Daemon          │
└─────────────────┘       │  Deletes ZIPs > 24h     │
  ║ = runs in parallel     └─────────────────────────┘
```

## Quick start

```bash
# 1. Clone and configure
cp .env.example .env

# 2. Run with Docker Compose (recommended)
docker-compose up --build

# 3. Open browser
# Frontend: http://localhost:8501
# API docs: http://localhost:8000/docs
```

## Local development

```bash
pip install -r requirements.txt

# Terminal 1 — backend
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — frontend
streamlit run frontend/app.py
```

## Running tests

```bash
pytest tests/ -v
```

## API reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/clarify` | Ask one clarifying question before pipeline |
| `POST` | `/generate-project` | Start full generation pipeline |
| `POST` | `/cancel/{job_id}` | Cancel a running/queued job |
| `POST` | `/regenerate-file` | Regenerate a single file with correction note |
| `GET` | `/files/{job_id}` | Live file tree during generation |
| `GET` | `/validate/{job_id}` | Re-run syntax checks + pytest |
| `GET` | `/status/{job_id}` | Full job status + logs |
| `GET` | `/download/{job_id}` | Download ZIP |
| `GET` | `/jobs` | List recent jobs |
| `GET` | `/health` | Backend + Ollama health |

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama API URL |
| `MODEL_FAST` | `qwen2.5-coder:1.5b` | Fast model name |
| `MODEL_BALANCED` | `qwen2.5-coder:7b` | Balanced model name |
| `MODEL_POWERFUL` | `qwen2.5-coder:7b` | Powerful model name |
| `LLM_TIMEOUT` | `180` | Per-call timeout in seconds |
| `LLM_MAX_RETRIES` | `3` | Retry attempts on timeout |
| `ZIP_RETENTION_HOURS` | `24` | Hours before old ZIPs are deleted |
| `CLEANUP_INTERVAL_SECONDS` | `3600` | How often cleanup runs |
| `LOG_LEVEL` | `INFO` | Python logging level |

## Supported project types

Student management · Inventory · Blog · Task manager · Employee management · CRUD dashboards · REST APIs

## Stack

- **Ollama** — local LLM runtime (models auto-downloaded)
- **ChromaDB** — persistent job + log storage
- **FastAPI** — async REST backend
- **Streamlit** — interactive frontend
- **Docker Compose** — one command to run everything

## License

MIT
