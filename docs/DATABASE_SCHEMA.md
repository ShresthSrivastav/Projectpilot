# Database Schema Report — ProjectPilot

## 1. Database Systems

ProjectPilot uses two data stores:

| Store | Purpose | Technology | Location |
|-------|---------|------------|----------|
| SQLite | Relational data (projects, API keys, analytics) | SQLAlchemy 2.0 | `./data/analytics.db` |
| ChromaDB | Vector store (job state, LLM context) | ChromaDB 0.4+ | `./data/chroma/` |

## 2. SQLite Schema

### 2.1. `projects` Table

```sql
CREATE TABLE projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id VARCHAR UNIQUE NOT NULL,       -- UUID generated at creation
    name VARCHAR NOT NULL,
    description TEXT,
    prompt TEXT NOT NULL,                     -- Original user prompt
    status VARCHAR DEFAULT 'pending',         -- pending|running|completed|failed|cancelled
    tech_stack VARCHAR,                       -- e.g., "fastapi,streamlit,sqlalchemy"
    job_dir VARCHAR,                          -- Path to generated project files
    zip_path VARCHAR,                         -- Path to ZIP archive
    completeness_score FLOAT DEFAULT 0.0,     -- 0-100%
    error_message TEXT,                       -- Failure reason if any
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);
```

**Indexes:**
- `idx_projects_project_id` UNIQUE on `project_id`
- `idx_projects_status` on `status`
- `idx_projects_created_at` on `created_at`

### 2.2. `api_keys` Table

```sql
CREATE TABLE api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash VARCHAR NOT NULL UNIQUE,         -- SHA-256 of API key
    name VARCHAR NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP
);
```

### 2.3. `analytics_events` Table

```sql
CREATE TABLE analytics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL,               -- step_start|step_end|gate_pass|gate_fail|error
    event_data TEXT,                           -- JSON blob with details
    duration_ms INTEGER,                       -- How long the event took
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(project_id)
);
```

**Indexes:**
- `idx_events_project` on `project_id`
- `idx_events_type` on `event_type`

## 3. ChromaDB Collections

### 3.1. `job_descriptions`
```
{
    "id": "job-<uuid>",
    "metadata": {
        "status": "running",
        "created_at": "2024-01-01T00:00:00",
        "tech_stack": "fastapi,streamlit,sqlalchemy"
    },
    "document": "Initial prompt + generated requirements JSON"
}
```

### 3.2. `project_artifacts`
```
{
    "id": "file-<hash>",
    "metadata": {
        "job_id": "<uuid>",
        "file_path": "backend/main.py",
        "file_type": "python"
    },
    "document": "Full file contents"
}
```

## 4. Entity-Relationship Diagram

```
┌─────────────┐       ┌──────────────────┐
│  projects   │ 1───N │ analytics_events │
│             │       │                  │
│ project_id  │◄──────┤ project_id       │
│ name        │       │ event_type       │
│ status      │       │ event_data       │
│ prompt      │       │ duration_ms      │
│ tech_stack  │       │ created_at       │
│ job_dir     │       └──────────────────┘
│ zip_path    │
│ score       │       ┌──────────────────┐
│ created_at  │       │   api_keys       │
└─────────────┘       │                  │
                      │ key_hash         │
┌─────────────┐       │ name             │
│  ChromaDB   │       │ is_active        │
│             │       │ created_at       │
│ job_desc    │       │ last_used_at     │
│ artifacts   │       └──────────────────┘
└─────────────┘
```

## 5. Migration History

| Migration | Date | Description |
|-----------|------|-------------|
| V1 (base) | Initial | `projects`, `api_keys` tables |
| V2 | 2024-03 | Add `analytics_events` table |
| V3 | 2024-06 | Add `completeness_score` to projects |
| V4 | 2024-09 | Add `error_message` to projects |
| V5 | 2024-12 | Add indexes for performance |

## 6. Data Cleanup Policy

- Job artifact directories: deleted after 24h (cleanup_service.py)
- Analytics events: retained 90 days
- ChromaDB collections: retained until job expires
- ZIP archives: retained 7 days
