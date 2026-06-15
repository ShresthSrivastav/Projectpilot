# ProjectPilot v5 — Upgrade Plan

## Current Architecture (v4.1)

```
Streamlit FE → FastAPI BE → Agent Pipeline (linear) → ChromaDB
  (8501)          (8000)      8 agents, single-threaded      (ephemeral)
```

**Existing agents:** RequirementAgent → PlannerAgent → CodeAgent → TestGenAgent → DebugAgent → DocsAgent → ValidationAgent → ZipService

**Key modules:** `services/llm_service.py`, `services/file_service.py`, `services/test_service.py`, `services/zip_service.py`, `services/cleanup_service.py`, `database/chroma_db.py`

**Requirements:** FastAPI 0.111.0, Streamlit 1.35.0, ChromaDB, Ollama, OpenAI SDK

---

## Upgrade Strategy: 3 Phases, All Non-Breaking

### Guiding Principles
1. Every new file is additive — zero changes to existing agent signatures
2. The existing `Orchestrator` becomes a sub-component of a new `Supervisor`
3. All new features start behind feature flags
4. New endpoints are additive, old ones remain untouched
5. Each new agent is a standalone module with `run()` entry point

---

## Phase 1: Foundation (Files 01–07)

### 01. `services/supervisor_service.py` — Supervisor Orchestration
- Wraps the existing `Orchestrator` in a new `Supervisor` that manages multiple agent "teams"
- Adds: agent routing, inter-agent messaging, parallel team execution
- API: `Supervisor.register_agent(name, module)`, `Supervisor.delegate(team, task)`, `Supervisor.broadcast(msg)`
- Maintains backward compat: old `Orchestrator` still usable directly
- Thread-safe agent registry with priority ordering

### 02. `agents/architect_agent.py` — Architect Agent
- Analyzes requirements and generates architecture diagrams (Mermaid.js)
- Designs system architecture, component relationships, data flow
- Produces: `ARCHITECTURE.md` with Mermaid diagrams, dependency graph
- Uses LLM (fast model) to generate diagram definitions
- Reuses existing `planner_agent` blueprint format

### 03. `agents/security_agent.py` — Security Auditor
- Scans generated code for OWASP Top 10 vulnerabilities
- Checks: SQL injection, XSS, hardcoded secrets, insecure deserialization, missing auth
- Produces: `SECURITY_REPORT.md` with severity ratings
- Uses regex patterns + LLM analysis (balanced model)
- Non-blocking (reports issues, doesn't stop pipeline)

### 04. `agents/performance_agent.py` — Performance Auditor
- Analyzes generated code for performance antipatterns
- Checks: N+1 queries, missing indexes, blocking calls in async paths, large payloads
- Produces: `PERFORMANCE_REPORT.md`
- Uses LLM analysis (fast model)

### 05. `agents/devops_agent.py` — DevOps Config Generator
- Generates docker-compose, Dockerfile improvements, CI/CD configs
- Detects project type and generates: `.github/workflows/ci.yml`, `Dockerfile.prod`, `.dockerignore`
- Reuses existing `Dockerfile` and `docker-compose.yml` as templates
- Adds deployment configs for common platforms (Render, Railway, Fly.io)

### 06. `agents/git_agent.py` — Git Integration
- Generates commit messages from diff analysis
- Generates PR descriptions and release notes
- Initializes git repos with `.gitignore`
- All operations are preview-only (user must confirm)
- Uses LLM (fast model) for message generation

### 07. `agents/bug_fixer_agent.py` — Bug-Fixing Agent
- Enhanced version of current DebugAgent logic
- Adds: root-cause analysis from pytest output, multi-file fix coordination, fix verification loop
- Autonomous fix-retest loop: fix → syntax check → pytest → repeat up to 3×
- Reuses existing `run_syntax_check` and `run_pytest` services

---

## Phase 2: Core Capabilities (Files 08–12)

### 08. `services/rag_service.py` — RAG Support
- Upload documentation, PDFs, project files as reference material
- Chunks documents, embeds with Ollama embeddings (nomic-embed-text), stores in ChromaDB
- Retrieves relevant chunks as context for LLM calls
- New collections: `rag_docs`, `rag_chunks`
- API endpoints: `POST /rag/upload`, `POST /rag/query`, `GET /rag/list`
- Chunking: 500-char windows with 50-char overlap
- Uses Ollama's embedding model (pulled automatically)

### 09. `database/memory_store.py` — Persistent Memory (SQLite)
- SQLite-backed persistent memory for cross-project learning
- Stores: agent decisions, fix patterns, user preferences, project metadata
- Tables: `agent_memory`, `fix_patterns`, `user_prefs`, `project_analytics`
- ChromaDB remains for: job state, logs, requirements, blueprints, RAG chunks
- SQLite for: long-term memory, analytics, patterns

### 10. `services/analytics_service.py` — Analytics Dashboard
- Tracks: agent execution time, token usage (from LLM structured logs), file counts, test results
- Stores aggregated metrics in SQLite (`memory_store.py`)
- Produces: project analytics summary, agent speed leaderboard, token cost estimates
- API endpoints: `GET /analytics/project/{job_id}`, `GET /analytics/overview`
- Frontend tab: "📊 Analytics"

### 11. `frontend/pages/analytics.py` — Analytics Dashboard UI
- Streamlit page showing: agent timing breakdown, token usage per agent, file generation timeline
- Charts: bar chart of agent durations, line chart of token usage, pie chart of file types
- Uses `altair` for charts (lightweight, plays well with Streamlit)
- Added as a 4th tab in the existing frontend

### 12. `frontend/pages/workspace.py` — Multi-Project Workspace
- Lists all projects with metadata (status, files, test results)
- Search/filter by name, status, date
- Compare two projects side-by-side
- Reuses existing job listing endpoints

---

## Phase 3: Advanced Features (Files 13–17)

### 13. `services/code_review_service.py` — Multi-Agent Code Review
- Runs review across 3 agents in parallel: Security, Performance, Quality
- Each agent reviews independently, then results are merged into a report
- Quality checks: type hints, docstrings, error handling, test coverage
- Produces: `CODE_REVIEW.md` with per-file findings and severity

### 14. `services/sandbox_service.py` — Local Code Execution Sandbox
- Executes generated code in a subprocess with timeout and resource limits
- Captures stdout, stderr, exit code, execution time
- Runs tests, lints (pyflakes), and static analysis (bandit if available)
- API: `POST /sandbox/run`, `POST /sandbox/test`
- Uses `subprocess` with `timeout` and `cwd` isolation

### 15. `services/diagram_service.py` — Architecture Diagram Generator
- Generates Mermaid.js diagrams from blueprint data
- Component diagram: shows agents, services, data flow
- ER diagram: shows database tables and relationships
- Sequence diagram: shows the generation pipeline flow
- Outputs Mermaid markdown that renders in GitHub/MkDocs

### 16. `agents/rag_enhanced_agent.py` — RAG-Enhanced Agent Base
- Base class for agents that can use RAG context
- Adds: `retrieve_context(query)`, `augment_prompt(prompt, context)`
- New agents can extend this; existing agents opt in by calling `augment_prompt()`
- Graceful degradation if RAG has no matching documents

### 17. `services/plugin_loader.py` — Plugin Architecture
- Discovers and loads agents from `agents/plugins/` directory
- Plugin manifest format (JSON): `{ "name": "...", "entry": "...", "hooks": [...] }`
- Hooks: `pre_generate`, `post_agent`, `pre_test`, `post_package`
- Registry of available plugins, enable/disable at runtime
- API: `GET /plugins`, `POST /plugins/{name}/toggle`

---

## Backward Compatibility Matrix

| Existing Feature | v5 Impact | Breaking? |
|---|---|---|
| `POST /generate-project` | Same request/response; Supervisor delegates to Orchestrator | No |
| `POST /clarify` | Unchanged | No |
| `POST /cancel/{job_id}` | Unchanged | No |
| `POST /regenerate-file` | Unchanged | No |
| `GET /files/{job_id}` | Unchanged | No |
| `GET /validate/{job_id}` | Unchanged | No |
| `GET /status/{job_id}` | New fields added (analytics, memory) | No |
| `GET /health` | Unchanged | No |
| `GET /jobs` | Unchanged | No |
| `GET /download/{job_id}` | Unchanged | No |
| Orchestrator class | Still exists, wrapped by Supervisor | No |
| All existing agents | Still importable with same `run()` signature | No |
| ChromaDB collections | New collections added, old ones unchanged | No |
| `llm_service.call_model()` | Unchanged | No |

---

## New Dependencies (add to requirements.txt)

```
# Phase 1 - RAG & Embeddings
pypdf>=4.0.0           # PDF parsing for RAG
altair>=5.3.0           # Analytics charts (lightweight)

# Phase 2 - Static Analysis
pyflakes>=3.2.0         # Fast linting
bandit>=1.7.8           # Security static analysis (optional, graceful fallback)

# Phase 3 - Diagrams
# (Mermaid is text-based, no extra dep)
```

---

## Migration Steps

1. Install new deps: `pip install pypdf altair pyflakes bandit`
2. Restart backend — new endpoints available immediately
3. New collections created in ChromaDB on first use
4. SQLite database created at `./memory_store/ProjectPilot_memory.db` on first use
5. RAG: upload docs via `POST /rag/upload` (file + optional tags)
6. Plugins: drop `.py` files into `agents/plugins/`, they auto-discover
7. Workspace view available in frontend as 4th tab

---

## File-by-File Implementation Order

```
Phase 1 (Foundation):
  01  services/supervisor_service.py       (new)
  02  agents/architect_agent.py            (new)
  03  agents/security_agent.py             (new)
  04  agents/performance_agent.py          (new)
  05  agents/devops_agent.py               (new)
  06  agents/git_agent.py                  (new)
  07  agents/bug_fixer_agent.py            (new)

Phase 2 (Core):
  08  services/rag_service.py              (new)
  09  database/memory_store.py             (new)
  10  services/analytics_service.py        (new)
  11  frontend/pages/analytics.py          (new)
  12  frontend/pages/workspace.py          (new)

Phase 3 (Advanced):
  13  services/code_review_service.py      (new)
  14  services/sandbox_service.py          (new)
  15  services/diagram_service.py          (new)
  16  agents/rag_enhanced_agent.py         (new)
  17  services/plugin_loader.py            (new)

Backend Updates:
  18  backend/main.py                      (modify — add new endpoints)
  19  frontend/app.py                      (modify — add new tabs)
  20  database/chroma_db.py                (modify — add RAG collections)
  21  requirements.txt                     (modify — add deps)
```

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| RAG embedding model fails to pull | Medium | Graceful fallback to no-RAG mode |
| SQLite concurrent writes from agents | Low | Per-agent transaction isolation |
| Plugin agent crashes main process | Medium | Subprocess isolation for plugins |
| LLM cost from additional agents | Low | All new agents use fast/balanced models |
| Frontend rendering slow with many jobs | Low | Pagination in workspace view |
