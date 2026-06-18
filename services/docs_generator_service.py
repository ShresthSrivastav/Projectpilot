"""Documentation Generator — auto-generates professional docs from source code.

Generates:
  - docs/architecture.md       — System architecture and component overview
  - docs/agents.md             — Agent descriptions and capabilities
  - docs/workflows.md          — Pipeline workflows and data flow
  - docs/deployment.md         — Deployment guide and configuration
  - docs/memory.md             — Memory and persistence layer
  - docs/plugins.md            — Plugin system and extension guide
  - docs/api.md                — Full API reference
  - docs/observability.md      — Monitoring and analytics
  - docs/security.md           — Security model and best practices
  - docs/roadmap.md            — Future development roadmap
  - docs/diagrams/             — Mermaid architecture diagrams

Regeneration: python -c "from services.docs_generator_service import generate_all; generate_all()"
"""
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DOCS_DIR = Path(os.getenv("DOCS_DIR", "./docs"))
DIAGRAMS_DIR = DOCS_DIR / "diagrams"
BASE_DIR = Path(os.getenv("GENERATED_PROJECTS_DIR", "./generated_projects")).resolve()


def generate_all(output_dir: str | None = None) -> dict[str, str]:
    docs_dir = Path(output_dir) if output_dir else DOCS_DIR
    diagrams_dir = docs_dir / "diagrams"
    docs_dir.mkdir(parents=True, exist_ok=True)
    diagrams_dir.mkdir(parents=True, exist_ok=True)

    generated = {}

    docs = {
        "architecture.md": _generate_architecture_doc,
        "agents.md": _generate_agents_doc,
        "workflows.md": _generate_workflows_doc,
        "deployment.md": _generate_deployment_doc,
        "memory.md": _generate_memory_doc,
        "plugins.md": _generate_plugins_doc,
        "api.md": _generate_api_doc,
        "observability.md": _generate_observability_doc,
        "security.md": _generate_security_doc,
        "roadmap.md": _generate_roadmap_doc,
    }

    for filename, generator_fn in docs.items():
        try:
            content = generator_fn()
            (docs_dir / filename).write_text(content, encoding="utf-8")
            generated[filename] = "ok"
            logger.info("Generated: %s", filename)
        except Exception as exc:
            generated[filename] = f"error: {exc}"
            logger.error("Failed to generate %s: %s", filename, exc)

    # Generate diagrams
    diagrams = {
        "system_architecture": _generate_system_architecture_mermaid,
        "agent_flow": _generate_agent_flow_mermaid,
        "repository_flow": _generate_repo_flow_mermaid,
        "deployment_flow": _generate_deployment_flow_mermaid,
    }
    for name, fn in diagrams.items():
        try:
            content = fn()
            (diagrams_dir / f"{name}.md").write_text(content, encoding="utf-8")
            generated[f"diagrams/{name}.md"] = "ok"
        except Exception as exc:
            generated[f"diagrams/{name}.md"] = f"error: {exc}"

    # Generate combined index
    index = _generate_index(list(docs.keys()))
    (docs_dir / "README.md").write_text(index, encoding="utf-8")
    generated["README.md"] = "ok"

    return generated


def _discover_agents() -> list[dict]:
    agents_dir = Path(__file__).parent.parent / "agents"
    agents = []
    if agents_dir.exists():
        for fp in sorted(agents_dir.glob("*_agent.py")):
            try:
                module_name = f"agents.{fp.stem}"
                import importlib
                mod = importlib.import_module(module_name)
                run_fn = getattr(mod, "run", None)
                doc = (mod.__doc__ or "").strip()[:500]
                agents.append({
                    "name": fp.stem.replace("_agent", "").replace("_", " ").title() + " Agent",
                    "module": fp.stem,
                    "file": str(fp.relative_to(agents_dir.parent)),
                    "description": doc,
                    "has_run_function": run_fn is not None,
                })
            except Exception as exc:
                agents.append({"name": fp.stem, "error": str(exc)[:100]})
    return agents


def _discover_routes() -> list[dict]:
    try:
        from backend.main import app
        routes = []
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                for method in route.methods:
                    if method in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                        routes.append({"method": method, "path": route.path})
        return routes
    except Exception as exc:
        return [{"error": str(exc)}]


# ── Document Generators ──────────────────────────────────────────────────────


def _generate_architecture_doc() -> str:
    agents = _discover_agents()
    routes = _discover_routes()
    lines = [
        "# System Architecture",
        "**Version:** 7.0.0",
        f"**Generated:** {datetime.utcnow().isoformat()}",
        "",
        "## Overview",
        "",
        "ProjectPilot is a production-grade autonomous software engineering platform.",
        "It uses a multi-agent architecture to generate, test, review, and deploy",
        "software projects based on natural language prompts.",
        "",
        "## Core Components",
        "",
        "### Backend (FastAPI)",
        "- **Port:** 8000",
        f"- **Routes:** {len(routes)}",
        "- **Framework:** FastAPI with Pydantic v2 validation",
        "",
        "### Frontend (Streamlit)",
        "- **Port:** 8501",
        "- **Framework:** Streamlit with real-time polling",
        "",
        "### Database",
        "- **ChromaDB:** Job state, requirements, blueprints, generation logs",
        "- **SQLite (Memory Store):** Agent memory, fix patterns, analytics, chat",
        "",
        "    ### LLM Providers",
        "| Provider | Type | Default Model |",
        "|----------|------|---------------|",
        "| local | Ollama (Gemma 4 12B) | gemma4:12b |",
        "| cloud | Google AI (Gemma 4 31B) | gemma-4-31b-it |",
        "",
        "## Agent Pipeline",
        "",
        "```mermaid",
        "graph LR",
        "    A[User Prompt] --> B[Requirement Agent]",
        "    B --> C[Planner Agent]",
        "    C --> D[Code Agent]",
        "    D --> E[Test Gen Agent]",
        "    E --> F[Debug Agent]",
        "    F --> G[Docs Agent]",
        "    G --> H[Validation Agent]",
        "    H --> I[Zip Service]",
        "    I --> J[Complete Project]",
        "```",
        "",
        "## Agent Statistics",
        "",
        "| Agent | Module | Run Function | Description |",
        "|-------|--------|-------------|-------------|",
    ]
    for a in agents:
        desc = a.get("description", "")[:80].replace("\n", " ")
        has_run = "yes" if a.get("has_run_function") else "no"
        lines.append(f"| {a['name']} | `{a.get('module', '')}` | {has_run} | {desc} |")
    lines.append("")
    return "\n".join(lines)


def _generate_agents_doc() -> str:
    agents = _discover_agents()
    lines = [
        "# Agents Reference",
        f"**Generated:** {datetime.utcnow().isoformat()}",
        "",
        "## Overview",
        f"ProjectPilot includes {len(agents)} agent modules that work together in a pipeline.",
        "",
        "## Agent Catalog",
        "",
    ]
    for a in agents:
        lines.append(f"### {a['name']}")
        lines.append(f"- **Module:** `{a.get('module', '')}`")
        lines.append(f"- **File:** `{a.get('file', '')}`")
        if a.get("description"):
            lines.append(f"- **Description:** {a['description']}")
        if a.get("has_run_function"):
            lines.append("- **Entry Point:** `run()` function")
        lines.append("")
    return "\n".join(lines)


def _generate_workflows_doc() -> str:
    return f"""# Workflows

**Generated:** {datetime.utcnow().isoformat()}

## Generation Pipeline

The primary workflow is the project generation pipeline:

1. **Clarify** — Requirement agent asks a clarifying question if the prompt is ambiguous
2. **Generate** — Full pipeline: requirements -> plan -> code -> tests -> docs -> validation -> zip
3. **Iterate** — Modify an existing project with new instructions
4. **Validate** — Re-run syntax checks and tests on demand
5. **Review** — AI-powered project review with recommendations

## Auto-Fix Loop

```mermaid
graph TD
    A[Generate Project] --> B[Run Tests]
    B --> C{{Tests Pass?}}
    C -->|Yes| D[Done]
    C -->|No| E[Collect Failures]
    E --> F[LLM Fixes Source Code]
    F --> G[Re-run Tests]
    G --> H{{Tests Pass?}}
    H -->|Yes| D
    H -->|No| I{{Max Attempts?}}
    I -->|No| F
    I -->|Yes| D
```

## Browser Testing Workflow

1. Create browser session
2. Navigate to target URL
3. Execute test script (click, fill, assert)
4. Capture screenshots
5. Review test results
6. Close session

## Repository Analysis Workflow

1. Clone repository
2. Scan all source files
3. Detect language and framework
4. Build dependency graph
5. Analyze architecture
6. Detect code smells and security issues
7. Generate missing tests
8. Apply automated fixes
9. Validate changes
10. Create pull request

## Data Flow

```mermaid
sequenceDiagram
    User->>Frontend: Submit prompt
    Frontend->>Backend: POST /generate-project
    Backend->>Orchestrator: Start pipeline
    Orchestrator->>Requirement Agent: Analyze prompt
    Requirement Agent->>Planner Agent: Requirements
    Planner Agent->>Code Agent: Blueprint
    Code Agent->>Test Gen Agent: Source files
    Test Gen Agent->>Debug Agent: Test files
    Debug Agent->>Docs Agent: Validated code
    Docs Agent->>Validation Agent: Docs
    Validation Agent->>Zip Service: Validation report
    Zip Service->>Backend: Project ZIP
    Backend->>Frontend: Job status + files
    Frontend->>User: Show results
```
"""


def _generate_deployment_doc() -> str:
    return f"""# Deployment Guide

**Generated:** {datetime.utcnow().isoformat()}

## Docker Deployment

### Prerequisites
- Docker 24+ and Docker Compose v2+
- Ollama running locally or accessible via network
- API key (optional): GOOGLE_API_KEY

### Quick Start

```bash
# Clone and start
git clone <repo> autodev-ai
cd autodev-ai
cp .env.example .env
# Edit .env with your API keys
docker compose up -d
```

### Production Deployment

```bash
# Build production image
docker build -t autodev-ai:latest .

# Run with production settings
docker run -d \\
  --name autodev-backend \\
  -p 8000:8000 \\
  -v ./chroma_data:/app/chroma_data \\
  -v ./generated_projects:/app/generated_projects \\
  -v ./memory_store:/app/memory_store \\
  --env-file .env \\
  autodev-ai:latest \\
  uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## Platform Deployments

### Render.com
```yaml
# render.yaml generated via POST /deploy/{{job_id}} target=render
```

### Railway.app
```json
// railway.json generated via POST /deploy/{{job_id}} target=railway
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| OLLAMA_BASE_URL | http://localhost:11434 | Ollama API endpoint |
| MODEL_LOCAL | gemma4:12b | Default local model (Gemma 4 12B) |
| GOOGLE_API_KEY | — | Google AI API key (Gemma 4 31B) |
| CLOUD_MODEL | gemma-4-31b-it | Cloud model name |
| LLM_TIMEOUT | 180 | LLM call timeout (seconds) |
| CHROMA_PATH | ./chroma_data | ChromaDB persistence path |
| LOG_LEVEL | INFO | Logging level |
"""
    # Note: The actual env table continues with all 25+ variables


def _generate_memory_doc() -> str:
    return f"""# Memory & Persistence

**Generated:** {datetime.utcnow().isoformat()}

## Overview

ProjectPilot uses a two-layer persistence architecture:

1. **ChromaDB** — Vector database for job state, requirements, blueprints, logs
2. **SQLite (Memory Store)** — Relational data for analytics, fix patterns, preferences, chat

## ChromaDB Collections

| Collection | Purpose | Schema |
|------------|---------|--------|
| jobs | Job state and metadata | status, progress_pct, file_count, test_* |
| generation_logs | Per-agent log entries | agent_name, log_level, message, timestamp |
| requirements | Parsed project requirements | JSON document per job |
| blueprints | Architecture blueprints | JSON document per job |

## SQLite Memory Tables

| Table | Purpose |
|-------|---------|
| agent_memory | Per-agent key-value memory across jobs |
| fix_patterns | Error signatures and successful fixes |
| user_prefs | User preferences and settings |
| project_analytics | Cross-project analytics and metrics |
| coding_preferences | Inferred coding style preferences |
| reusable_components | Reusable code patterns and templates |
| project_insights | Learnings extracted from completed projects |
| chat_conversations | Chat history |
| chat_messages | Individual chat messages |
| github_connections | GitHub API credentials |
| github_repos | Cached repository metadata |

## Long-Term Learning

The memory system enables cross-project learning:

1. **Fix Patterns** — When a fix succeeds, its signature is stored
2. **Coding Preferences** — Stack choices and patterns are tracked
3. **Reusable Components** — Common code patterns are saved for reuse
4. **Project Insights** — Lessons learned are extracted and stored

## Embedding Service

For semantic search, the embedding service uses Ollama's embedding API:
- Default model: `all-minilm:l6-v2`
- Fallback: Zero vector (384-dim) if Ollama unavailable
- Used by: ChromaDB collections with `embedding_function`
"""


def _generate_plugins_doc() -> str:
    return f"""# Plugin System

**Generated:** {datetime.utcnow().isoformat()}

## Overview

The plugin system allows extending ProjectPilot with custom agent behaviors.
Plugins are discovered automatically from `agents/plugins/` directory.

## Plugin Structure

```
agents/plugins/
  my_plugin.py          # Python plugin file
  my_plugin.json        # Optional manifest
```

## Plugin Manifest (my_plugin.json)

```json
{{
  "name": "My Plugin",
  "version": "1.0.0",
  "description": "Description of what this plugin does",
  "entry": "my_plugin.py",
  "hooks": ["pre_generate", "post_generate"]
}}
```

## Hook Points

| Hook | Timing | Context |
|------|--------|---------|
| pre_generate | Before generation pipeline | prompt, job_id, model |
| post_generate | After generation completes | job_id, files, results |
| pre_review | Before AI review | job_id, project_data |
| post_review | After review completes | review_results |

## Plugin API

```python
def run(context: dict) -> dict:
    \"\"\"Main entry point for the plugin.\"\"\"
    # Your code here
    return {{"status": "ok", "result": ...}}

def pre_generate(context: dict) -> dict:
    \"\"\"Hook called before generation.\"\"\"
    return {{"status": "ok"}}

def post_generate(context: dict) -> dict:
    \"\"\"Hook called after generation.\"\"\"
    return {{"status": "ok"}}
```

## Available Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | /plugins | List all plugins |
| POST | /plugins/reload | Reload all plugins |
| POST | /plugins/{{name}}/toggle | Enable/disable plugin |
"""


def _generate_api_doc() -> str:
    routes = _discover_routes()
    lines = [
        "# API Reference",
        f"**Generated:** {datetime.utcnow().isoformat()}",
        f"**Total routes:** {len(routes)}",
        "",
        "## Endpoints",
        "",
        "| Method | Path | Description |",
        "|--------|------|-------------|",
    ]
    for r in sorted(routes, key=lambda x: x["path"]):
        descs = {
            "/health": "Health check with provider status",
            "/providers": "List available LLM providers",
            "/metrics": "System metrics and analytics",
            "/generate-project": "Start new project generation",
            "/clarify": "Get clarifying question for a prompt",
            "/cancel/": "Cancel a running job",
            "/regenerate-file": "Regenerate a single file",
            "/status/": "Get job status",
            "/files/": "List project files",
            "/read-project-file/": "Read a project file's content",
            "/validate/": "Run syntax and test validation",
            "/review/": "Run AI project review",
            "/fix-tests/": "Fix failing tests automatically",
            "/iterate/": "Modify an existing project",
            "/changelog/": "Get project changelog",
            "/download/": "Download project ZIP",
            "/jobs": "List recent jobs",
            "/autofix/": "Iterative auto-fix loop",
            "/sandbox/": "Docker sandbox execution",
            "/workspace/": "Workspace file CRUD",
            "/deploy/": "Generate deployment configs",
            "/memory/": "Memory and insights",
            "/browser/": "Browser automation",
            "/repo/": "Repository analysis",
            "/dashboard/": "Agent dashboard and telemetry",
            "/chat": "Chat with AI assistant",
            "/github": "GitHub integration",
            "/rag": "RAG document management",
            "/supervisor": "Supervisor agent delegation",
            "/diagram": "Architecture diagrams",
            "/code-review": "AI code review",
            "/plugins": "Plugin management",
        }
        desc = ""
        for key, val in descs.items():
            if key in r["path"]:
                desc = val
                break
        lines.append(f"| {r['method']} | `{r['path']}` | {desc} |")
    return "\n".join(lines) + "\n"


def _generate_observability_doc() -> str:
    return f"""# Observability

**Generated:** {datetime.utcnow().isoformat()}

## Monitoring Endpoints

| Endpoint | Description |
|----------|-------------|
| GET /health | System health + provider availability |
| GET /metrics | Token usage, analytics summary, timestamp |
| GET /dashboard/status | Real-time agent status + telemetry |
| WS /dashboard/stream | WebSocket event stream |

## Metrics

- **Token Usage:** Tracked per LLM call with reset per pipeline
- **Agent Telemetry:** Status, runtime, success/failure counts
- **Cost Analytics:** Estimated cost based on token usage
- **Memory Usage:** Process RSS and CPU percentage (requires psutil)

## Logging

Structured JSON logging format:
```json
{{"time":"2024-01-01T00:00:00Z","level":"INFO","event":"llm_call_ok","model":"gemma4:12b","tokens":150,"duration_ms":3200,"provider":"local"}}
```

## Analytics Dashboard

The frontend provides:
- Project overview (total projects, tokens, files, tests)
- Per-project statistics
- Agent activity timeline
- Cost breakdown

## Agent Dashboard (v7.0.0+)

Real-time monitoring via:
- REST endpoint: `GET /dashboard/status`
- WebSocket: `WS /dashboard/stream`
- Frontend timeline view
- Execution graph visualization
"""


def _generate_security_doc() -> str:
    return f"""# Security Model

**Generated:** {datetime.utcnow().isoformat()}

## Overview

ProjectPilot implements security at multiple layers:

1. **Code Analysis** — Static security scanning in Security Agent
2. **Network Isolation** — Docker sandbox with no network access
3. **URL Validation** — Browser agent validates and restricts URLs
4. **Path Traversal** — All file operations check path boundaries
5. **API Key Management** — Keys stored in environment only

## Security Agent Checks

| Check | Severity | Pattern |
|-------|----------|---------|
| SQL Injection | HIGH | Raw string formatting in SQL queries |
| Hardcoded API Key | HIGH | Inline secrets and credentials |
| Hardcoded Password | HIGH | Plain text passwords in code |
| XSS | HIGH | Unsafe template rendering |
| Insecure Deserialization | HIGH | pickle, yaml.load, marshal |
| Path Traversal | HIGH | Unsanitized file paths |
| Debug Mode | MEDIUM | debug=True in production |
| Missing Auth | MEDIUM | Routes without authentication |
| SSTI | HIGH | Server-side template injection |
| Sensitive Data Exposure | LOW | Logging sensitive information |

## Sandbox Security

- **Network:** `--network=none` — no network access
- **Memory:** Configurable limit (`SANDBOX_MEMORY`, default 256m)
- **CPU:** Configurable limit (`SANDBOX_CPU`, default 0.5)
- **Process:** `--pids-limit=50` — prevents fork bombs
- **Filesystem:** `--read-only` — read-only container
- **Cleanup:** Containers and images removed after execution

## Browser Agent Security

- **URL Validation:** Scheme, host, and path validation
- **Domain Blocklist:** Local/internal IPs blocked by default
- **Domain Allowlist:** Optional restricted domain list
- **Headless Only:** No visible browser window
- **Session Isolation:** Each session in isolated context
"""


def _generate_roadmap_doc() -> str:
    return f"""# Roadmap

**Generated:** {datetime.utcnow().isoformat()}

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| v4.0.0 | — | Initial multi-agent pipeline, ChromaDB persistence |
| v5.0.0 | — | RAG, Analytics, Diagrams, Supervisor, Plugins |
| v6.0.0 | — | GitHub integration, Chat, Webhooks |
| v7.0.0 | 2024-06 | Browser Agent, Repo Analyzer, Live Dashboard, Professional Docs |

## v7.0.0 Features

1. **Browser Agent** — Playwright-based browser automation for testing
2. **Repository Analyzer** — Deep code analysis with auto PR generation
3. **Live Agent Dashboard** — Real-time WebSocket-based monitoring
4. **Professional Docs** — Auto-generated documentation system

## Planned Features

### v8.0.0 — Enterprise Scale
- Multi-user authentication and RBAC
- Team workspaces and collaboration
- Advanced CI/CD integration
- On-premise Kubernetes deployment

### v9.0.0 — AI-Native IDE
- VS Code extension with real-time agent collaboration
- Intelligent code completion from generated components
- Visual pipeline builder
- Natural language query interface

### v10.0.0 — Autonomous Platform
- Self-improving agents that learn from usage patterns
- Automated deployment and scaling
- Cross-project knowledge transfer
- Business metric integration

## Contributing

See [Plugin System](plugins.md) for extension points.
"""


def _generate_index(doc_files: list[str]) -> str:
    lines = [
        "# ProjectPilot Documentation",
        "",
        "**Version 7.0.0** — Production-Grade Autonomous Software Engineering Platform",
        "",
        "## Contents",
        "",
    ]
    for fname in sorted(doc_files):
        name = fname.replace(".md", "").replace("_", " ").title()
        lines.append(f"- [{name}]({fname})")
    lines.extend([
        "",
        "## Diagrams",
        "",
        "- [System Architecture](diagrams/system_architecture.md)",
        "- [Agent Flow](diagrams/agent_flow.md)",
        "- [Repository Flow](diagrams/repository_flow.md)",
        "- [Deployment Flow](diagrams/deployment_flow.md)",
        "",
        "## Quick Links",
        "",
        "- [API Reference](api.md)",
        "- [Deployment Guide](deployment.md)",
        "- [Security Model](security.md)",
        "- [Plugin Development](plugins.md)",
    ])
    return "\n".join(lines)


# ── Mermaid Diagram Generators ───────────────────────────────────────────────


def _generate_system_architecture_mermaid() -> str:
    return """# System Architecture Diagram

```mermaid
graph TB
    subgraph Frontend["Streamlit Frontend :8501"]
        UI[User Interface]
        CHAT[Chat Interface]
        DASH[Dashboard]
    end

    subgraph Backend["FastAPI Backend :8000"]
        API[API Layer - 92 Routes]
        ORC[Orchestrator]
        SUP[Supervisor]
        CHATB[Chat Service]
    end

    subgraph Agents["Agent Layer"]
        REQ[Requirement Agent]
        PLAN[Planner Agent]
        CODE[Code Agent]
        TEST[Test Gen Agent]
        DEBUG[Debug Agent]
        DOCS[Docs Agent]
        VALID[Validation Agent]
        SEC[Security Agent]
        BROWSER[Browser Agent]
        REPO[Repo Analyzer]
    end

    subgraph Services["Service Layer"]
        LLM[LLM Service]
        CHROM[ChromaDB Service]
        MEM[Memory Service]
        SAND[Docker Sandbox]
        DEPLOY[Deployment Service]
        DOCGEN[Docs Generator]
        DASHBOARD[Dashboard Service]
    end

    subgraph Storage["Persistence Layer"]
        CHROMADB[(ChromaDB)]
        SQLITE[(SQLite Memory)]
        FILES[(File System)]
    end

    subgraph External["External"]
        OLLAMA[Ollama - Local LLMs]
        GOOGLE[Google Gemini API]
        OPENAI[OpenAI API]
        DEEPSEEK[DeepSeek API]
        GITHUB[GitHub API]
        DOCKER[Docker Engine]
    end

    UI --> API
    CHAT --> CHATB
    DASH --> DASHBOARD

    API --> ORC
    API --> SUP
    ORC --> Agents
    SUP --> Agents
    Agents --> LLM
    CHATB --> LLM

    LLM --> OLLAMA
    LLM --> GOOGLE
    LLM --> OPENAI
    LLM --> DEEPSEEK

    Agents --> CHROM
    Agents --> MEM
    Agents --> SAND

    CHROM --> CHROMADB
    MEM --> SQLITE
    Agents --> FILES

    API --> GITHUB
    API --> DOCKER
    API --> DEPLOY
    API --> DOCGEN
    API --> BROWSER
    API --> REPO
```
"""


def _generate_agent_flow_mermaid() -> str:
    return """# Agent Flow Diagram

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant API as Backend API
    participant ORC as Orchestrator
    participant LLM as LLM Service
    participant Memory as Memory Store

    User->>Frontend: Submit prompt
    Frontend->>API: POST /generate-project
    API->>ORC: Start pipeline
    ORC->>LLM: Requirement Agent
    LLM-->>ORC: Requirements JSON
    ORC->>Memory: Store requirements
    ORC->>LLM: Planner Agent
    LLM-->>ORC: Blueprint
    ORC->>LLM: Code Agent
    LLM-->>ORC: Source files
    ORC->>LLM: Test Gen Agent
    LLM-->>ORC: Test files
    ORC->>LLM: Debug Agent
    LLM-->>ORC: Fixed code
    ORC->>LLM: Docs Agent
    LLM-->>ORC: README.md
    ORC->>LLM: Validation Agent
    LLM-->>ORC: Validation report
    ORC->>Memory: Save analytics
    ORC-->>API: Job complete
    API-->>Frontend: Status update
    Frontend-->>User: Show project
```
"""


def _generate_repo_flow_mermaid() -> str:
    return """# Repository Analysis Flow

```mermaid
graph LR
    REPO[Git Repository] --> CLONE[Clone]
    CLONE --> SCAN[Scan Files]
    SCAN --> LANG[Detect Language]
    LANG --> FRAME[Detect Framework]
    FRAME --> ARCH[Build Architecture]
    ARCH --> DEPS[Dependency Graph]
    DEPS --> SMELLS[Code Smells]
    SMELLS --> SEC[Security Scan]
    SEC --> QUALITY[Quality Metrics]
    QUALITY --> COVERAGE[Test Coverage]
    COVERAGE --> FIX[Generate Fixes]
    FIX --> TESTS[Generate Tests]
    TESTS --> VALIDATE[Run Validation]
    VALIDATE --> COMMIT[Git Commit]
    COMMIT --> PUSH[Git Push]
    PUSH --> PR[Create Pull Request]
    PR --> REPORTS[Generate Reports]
```
"""


def _generate_deployment_flow_mermaid() -> str:
    return """# Deployment Flow

```mermaid
graph TB
    subgraph Dev["Development"]
        CODE[Source Code]
        BUILD[Docker Build]
        TEST[Test Suite]
    end

    subgraph DeployTargets["Deploy Targets"]
        DOCKER[Docker Compose]
        RENDER[Render.com]
        RAILWAY[Railway.app]
        MANUAL[Manual]
    end

    subgraph Services["Required Services"]
        OLLAMA[Ollama]
        CHROMA[ChromaDB]
        MEMORY[Memory Store]
    end

    CODE --> BUILD
    BUILD --> TEST
    TEST --> DOCKER
    TEST --> RENDER
    TEST --> RAILWAY
    TEST --> MANUAL

    DOCKER --> OLLAMA
    DOCKER --> CHROMA
    DOCKER --> MEMORY
    RENDER --> CHROMA
    RAILWAY --> MEMORY
```
"""
