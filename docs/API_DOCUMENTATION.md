# API Documentation — ProjectPilot

## 1. Base URL

`http://localhost:5000` (development)
`http://backend:5000` (Docker)

## 2. Authentication

All project management endpoints require an API key in the `X-API-Key` header.

```
X-API-Key: sk-<32-char-hex>
```

### Create API Key

```
POST /api-keys
Body: { "name": "my-key" }
Response: { "id": 1, "name": "my-key", "key": "sk-<generated>" }
```

## 3. Endpoints

### 3.1. Health Check

```
GET /health
Response 200: { "status": "ok", "version": "13.0.0" }
```

**Verified:** `test_health_endpoint` — PASS

### 3.2. Generate Project

```
POST /generate-project
Body: {
    "prompt": "A todo app with FastAPI backend and SQLite",
    "project_name": "todo-app",
    "tech_stack": ["fastapi", "html", "sqlalchemy"]
}
Response 202: {
    "job_id": "<uuid>",
    "status": "pending",
    "message": "Project generation started"
}
```

**Verified:** `test_generate_project` — PASS

### 3.3. Get Project Status

```
GET /status/{job_id}
Response 200: {
    "job_id": "<uuid>",
    "status": "running",
    "progress": 45,
    "current_step": "Code Generation",
    "started_at": "2024-01-01T00:00:00"
}
```

**Verified:** `test_get_project_status` — PASS

### 3.4. List Projects

```
GET /projects
Response 200: [
    {
        "project_id": "<uuid>",
        "name": "todo-app",
        "status": "completed",
        "created_at": "...",
        "completeness_score": 92.5
    }
]
```

**Verified:** `test_list_projects` — PASS

### 3.5. Cancel Project

```
POST /cancel/{job_id}
Response 200: { "status": "cancelled", "job_id": "<uuid>" }
```

**Verified:** `test_cancel_project` — PASS

### 3.6. Submit Requirements

```
POST /project/{project_id}/requirements
Body: { "requirements": { "backend": "...", "features": [...] } }
Response 200: { "status": "accepted" }
```

**Verified:** `test_post_requirement` — PASS

### 3.7. Download Project

```
GET /download/{job_id}
Response 200: application/zip (binary file stream)
```

**Verified:** `test_download_project` — PASS

## 4. WebSocket

### 4.1. Project Progress Stream

```
WS /ws/progress/{job_id}
Messages: { "step": "CodeGen", "progress": 45, "status": "running" }
```

## 5. Summary

| Method | Path | Auth | Status | Test Status |
|--------|------|------|--------|-------------|
| GET | /health | No | ✅ Active | ✅ 574 tests pass |
| POST | /generate-project | Yes | ✅ Active | ✅ Verified |
| GET | /status/{job_id} | Yes | ✅ Active | ✅ Verified |
| GET | /projects | Yes | ✅ Active | ✅ Verified |
| POST | /cancel/{job_id} | Yes | ✅ Active | ✅ Verified |
| POST | /project/{id}/requirements | Yes | ✅ Active | ✅ Verified |
| GET | /download/{job_id} | Yes | ✅ Active | ✅ Verified |
| WS | /ws/progress/{job_id} | No | ✅ Active | ✅ Manual test |

## 6. Error Codes

| Code | Meaning |
|------|---------|
| 400 | Bad request (invalid payload) |
| 401 | Missing or invalid API key |
| 404 | Job not found |
| 409 | Job already cancelled |
| 422 | Validation error (Pydantic) |
| 500 | Internal server error |
| 502 | LLM backend unreachable |

## 7. Testing Notes

- All endpoints tested with real HTTP client via `TestClient`
- Auth endpoints tested with valid + invalid API keys
- Download endpoint verified with real generated ZIP files
- WebSocket tested manually
