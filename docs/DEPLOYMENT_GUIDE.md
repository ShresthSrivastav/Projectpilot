# Deployment Guide — ProjectPilot

## 1. Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| Docker | 24+ | `docker --version` |
| Docker Compose | 2.23+ | `docker compose version` |
| Python | 3.11+ | `python --version` |
| Git | 2.40+ | `git --version` |
| Disk Space | 10GB+ | `df -h .` |
| RAM | 4GB+ | `free -h` |
| GPU (optional) | CUDA 12+ | `nvidia-smi` (for local LLMs) |

## 2. Quick Start (Docker)

```bash
# 1. Clone
git clone <repo> autodev-ai
cd autodev-ai

# 2. Configure
cp .env.example .env
# Edit .env: set API keys (Gemini, etc.)

# 3. Build & Start
docker compose up --build -d

# 4. Verify
curl http://localhost:8000/health
# Expected: {"status":"ok","version":"13.0.0"}

# 5. Access
# Frontend: http://localhost:8501
# Backend:  http://localhost:8000
# API Docs: http://localhost:8000/docs
```

## 3. Quick Start (Local)

```bash
# 1. Setup Python
python -m venv venv
source venv/bin/activate  # Linux/Mac
.\venv\Scripts\Activate   # Windows

# 2. Install
pip install -r requirements.txt

# 3. Configure
cp .env.example .env
# Edit .env: set API keys

# 4. Start Backend
python backend/main.py &
# Listening on port 8000

# 5. Start Frontend
streamlit run frontend/app.py &
# Listening on port 8501
```

## 4. Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | Yes | — | Google Gemini API key |
| `DATABASE_URL` | No | `sqlite:///./data/analytics.db` | SQLite path |
| `CHROMA_PERSIST_DIR` | No | `./data/chroma` | ChromaDB directory |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `MAX_HEALING_ATTEMPTS` | No | `3` | Max repair loop iterations |
| `HEALING_FIX_TIMEOUT` | No | `120` | Timeout per fix (seconds) |
| `SKIP_RUNTIME_VALIDATION` | No | `false` | Skip runtime gate |
| `SKIP_IMPORT_VALIDATION` | No | `false` | Skip import gate |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Local LLM URL |
| `EXPORT_DIR` | No | `./exports` | Generated ZIP output |

## 5. Docker Images

| Service | Image | Ports | Volumes | Depends On |
|---------|-------|-------|---------|------------|
| backend | autodev-ai-backend | 8000:8000 | ./data:/app/data, ./exports:/app/exports | — |
| frontend | autodev-ai-frontend | 8501:8501 | — | backend |

## 6. Production Deployment

### 6.1. Single Host

```bash
docker compose -f docker-compose.prod.yml up -d
```

### 6.2. Load Balancing

```
nginx/
├── backend  → upstream backend:8000 (workers=4)
├── frontend → upstream frontend:8501
└── static   → /app/exports (ZIP downloads)
```

### 6.3. SSL (Let's Encrypt)

```bash
docker run -d --name nginx-ssl \
  -v ./nginx.conf:/etc/nginx/nginx.conf \
  -v /etc/letsencrypt:/etc/letsencrypt \
  -p 443:443 \
  nginx:alpine
```

## 7. Monitoring

| Tool | Endpoint | Purpose |
|------|----------|---------|
| Health Check | GET /health | Liveness probe |
| Metrics | GET /metrics | Prometheus (if enabled) |
| Logs | docker logs -f backend | Container logs |
| Debug | GET /debug | Diagnostic info |

## 8. Backup & Restore

### Backup
```bash
# SQLite
cp ./data/analytics.db ./backups/analytics-$(date +%F).db

# ChromaDB
cp -r ./data/chroma ./backups/chroma-$(date +%F)

# Exports
cp -r ./exports ./backups/exports-$(date +%F)
```

### Restore
```bash
cp ./backups/analytics-2024-01-01.db ./data/analytics.db
```

## 9. Cleanup

```bash
# Remove old artifacts (24h TTL)
python -m backend.services.cleanup_service

# Remove all artifacts
rm -rf ./exports/* ./data/chroma/*

# Full reset
docker compose down -v
rm -rf ./data ./exports
```

## 10. Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| Backend won't start | Port 8000 in use | `netstat -ano | findstr :8000`, kill process |
| Frontend won't start | Port 8501 in use | Same as above |
| LLM returns 500 | Invalid API key | Check `.env` GEMINI_API_KEY |
| Tests fail | Python version | Ensure 3.11+ |
| Docker build slow | No cache | `docker compose build --no-cache` (once) |
| ZIP download fails | Export dir missing | `mkdir -p exports` |
