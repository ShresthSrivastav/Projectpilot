# Architecture Report — ProjectPilot

## 1. System Overview

ProjectPilot is an autonomous software engineering platform. Given a natural language prompt, it generates a complete, tested, validated software project through a pipeline of AI agents and validation gates.

## 2. Architecture Style

**Event-driven Pipeline Architecture** — each step is a discrete agent or validator. Steps communicate via a shared job context (dictionary). The orchestrator manages the sequence and handles failures through a self-healing repair loop.

## 3. Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    USER INTERFACE                        │
│  Streamlit (port 8501) ↔ FastAPI (port 8000) ↔ Client   │
└──────────────────────┬──────────────────────────────────┘
                       │ POST /generate-project
                       │ GET /status/{job_id}
                       ▼
┌─────────────────────────────────────────────────────────┐
│              ORCHESTRATOR AGENT                          │
│  agents/orchestrator_agent.py                            │
│                                                         │
│  Steps: 20-30 Planner (generate blueprint)              │
│         30-60 CodeGen (write code)                       │
│         70-90 TestGen (write tests)                      │
│         95   Security Validator                          │
│         97   Acceptance Gates (20 gates)                 │
│         98   Completeness Scorer                         │
│         100  ZipService (package deliverable)            │
└──────────────────────┬──────────────────────────────────┘
                       │
    ┌──────────────────┼──────────────────┐
    ▼                  ▼                  ▼
┌──────────┐    ┌────────────┐    ┌──────────────┐
│ PLANNER  │    │  CODE      │    │  TEST GEN    │
│ AGENT    │    │  AGENT     │    │  AGENT       │
│ (reqs +  │    │  (python   │    │  (generates  │
│  plans)  │    │   files)   │    │   tests)     │
└──────────┘    └────────────┘    └──────────────┘
                      │
                      ▼
                ┌────────────┐
                │  DEBUG     │
                │  AGENT     │
                │  (fixes    │
                │   code)    │
                └────────────┘
                      │
                      ▼
                ┌────────────────────────────────┐
                │    20-VALIDATION GATES          │
                │  services/acceptance_gates.py   │
                │  (each gate = validator class)  │
                └────────────────────────────────┘
                      │
                      ▼
                ┌────────────────────────┐
                │  COMPLETENESS SCORER   │
                │  services/completeness │
                │  _scorer.py            │
                └────────────────────────┘
                      │
                      ▼
                ┌────────────────────────┐
                │  ZIP SERVICE           │
                │  services/zip_service  │
                │  .py                   │
                └────────────────────────┘
```

## 4. Backend Architecture

```
backend/
├── main.py              — FastAPI entry point (routes, CORS, lifespan)
├── config.py            — Environment configuration
├── routers/
│   ├── project.py       — Project generation + status endpoints
│   └── health.py        — Health check
├── models/
│   ├── project.py       — SQLAlchemy project model
│   └── api_key.py       — API key model
├── schemas/
│   └── project.py       — Pydantic request/response schemas
├── services/
│   ├── acceptance_gates.py        — 20-gate validation orchestration
│   ├── import_validator.py        — Gate 2: Import resolution
│   ├── syntax_validator.py        — Gate 3: Syntax checking
│   ├── test_runner.py             — Gate 20: Test execution
│   ├── runtime_validator.py       — Gate 7: Backend startup
│   ├── security_validator.py      — Gate 14: Security scanning
│   └── completeness_scorer.py     — Post-validation scoring
├── db/
│   └── database.py       — SQLite + session management
├── utils/
│   └── chroma_store.py   — ChromaDB job state persistence
└── agents/
    ├── orchestrator_agent.py  — Main pipeline controller
    ├── requirement_agent.py   — Requirement parser
    ├── planner_agent.py       — Implementation planner
    ├── code_agent.py          — Code generation
    ├── test_gen_agent.py      — Test generation
    └── debug_agent.py         — Code repair
```

## 5. Frontend Architecture

```
frontend/
├── app.py               — Streamlit entry point
├── components/
│   ├── project_form.py  — Input form for new project
│   ├── progress.py      — Live pipeline progress
│   ├── file_viewer.py   — Project file browser
│   └── results.py       — Download + report display
├── api/
│   └── client.py        — HTTP client to backend
└── pages/
    ├── generate.py      — Generate new project
    └── status.py        — View project status
```

## 6. Data Flow

```
1. User submits prompt → frontend/ → POST /generate-project
2. Backend creates job_id → returns immediately
3. Background thread runs pipeline:
   a. RequirementAgent → parsed requirements JSON
   b. PlannerAgent → task breakdown + blueprint
   c. CodeAgent → writes source files to job_dir
   d. DebugAgent → syntax-check + fix
   e. TestGenAgent → writes test files
   f. Acceptance Gates (20 gates) → validate project
   g. CompletenessScorer → score 0-100%
   h. ZipService → package as ZIP
4. Frontend polls GET /status/{job_id} for progress
5. User downloads ZIP or views reports
```

## 7. Technology Stack

| Component | Technology | Version |
|-----------|------------|---------|
| Backend | FastAPI | 0.104+ |
| Frontend | Streamlit | 1.28+ |
| Database | SQLAlchemy + SQLite | 2.0+ |
| Vector Store | ChromaDB | 0.4+ |
| LLM Backend | Google Gemini / Ollama | — |
| Validation | ast, py_compile, pytest | stdlib |
| Security | Bandit-style AST scanner | custom |
| Deployment | Docker | 24+ |
| Async | asyncio + threading | stdlib |
| CI | GitHub Actions | — |

## 8. Container Architecture

```
┌─────────────────────────────────────────┐
│            DOCKER COMPOSE                │
│                                         │
│  ┌──────────────┐  ┌────────────────┐   │
│  │  backend      │  │  frontend      │   │
│  │  port 8000    │  │  port 8501     │   │
│  └──────┬───────┘  └───────┬────────┘   │
│         │  HTTP             │            │
│         └────────┬──────────┘            │
│                  ▼                       │
│         ┌────────────────┐               │
│         │  volumes:       │               │
│         │  - ./data       │               │
│         │  - ./exports    │               │
│         └────────────────┘               │
└─────────────────────────────────────────┘
```

## 9. Deployment Architecture

```
Production:
  Docker host → docker-compose up -d
  Backend: port 8000, workers=4 (uvicorn)
  Frontend: port 8501, streamlit run
  Persistent: ./data (ChromaDB + SQLite)
  Cleanup: 24h TTL on job artifacts

Local Development:
  python backend/main.py (port 8000)
  streamlit run frontend/app.py (port 8501)
```

## 10. Failure Modes

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Cloud LLM 500 | HTTP error in DebugAgent | Fallback to local Ollama |
| Syntax error in generated code | Gate 3 (Syntax Validation) | DebugAgent repair loop |
| Import resolution error | Gate 2 (Import Validation) | DebugAgent repair loop |
| Tests fail | Gate 20 (Test Validation) | DebugAgent repair loop |
| Dependency install failure | Gate 1 (Dependency Validation) | Individual dep install |
| Runtime startup failure | Gate 7 (Startup Validation) | DebugAgent repair loop |
| Security finding | Gate 14 (Security Validation) | Report only (block on critical) |
