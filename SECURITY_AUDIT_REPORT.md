# Security Audit Report — ProjectPilot v13.0

**Audit Date:** 2026-06-12  
**Scope:** Full platform audit — 20 security areas  
**Auditor:** Principal Platform Security Engineer  

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Security Score** | **62/100** |
| **Critical Findings** | **3** (release gate: must be 0) |
| **High Findings** | **2** (release gate: must be ≤ 3) |
| **Medium Findings** | **17** |
| **Low Findings** | **16** |
| **Findings Fixed** | **12** |
| **Files Modified** | **8** |
| **Release Ready?** | **NO** — critical findings remain |

---

## Scoring Breakdown

| Category | Weight | Score |
|----------|--------|-------|
| No authentication on API | -20 | |
| Real API key in .env | -15 | |
| Container runs as root | -10 | |
| Unpinned base images | -5 | |
| No request size limits | -5 | |
| Undocumented env vars (26) | -3 | |
| Overly permissive deps | -2 | |
| Race conditions (unlocked reads) | -2 | |
| **Total Deduction** | | **-62** |
| **Final Score** | | **38/100** |

---

## Vulnerability Register

### CRITICAL (3 open)

#### C-01: No Authentication on Any API Endpoint

| Field | Value |
|-------|-------|
| **Location** | `backend/main.py` — all 269+ routes |
| **Issue** | Zero authentication on any endpoint. No `Depends()`, no JWT, no API key, no auth middleware. |
| **Impact** | Any network actor can invoke any API: execute arbitrary code, read/write files, run LLM debates, deploy projects, access GitHub tokens, modify workspaces. |
| **Exploit Scenario** | Attacker on same network calls `POST /sandbox/run` with arbitrary Python code, or `POST /supervisor/run-agent/{name}` to execute any agent, or `POST /github/connect` with stolen credentials. |
| **Fix Applied** | None — requires architectural change. Added `_resolve_job_path()` and `_validate_file_path()` helpers to reduce blast radius of path-based attacks. |
| **Residual Risk** | **CRITICAL** — this is the single largest security gap. Needs auth middleware (shared API key via header) as minimum. |

#### C-02: Real API Key in Plaintext `.env` File

| Field | Value |
|-------|-------|
| **Location** | `.env` line 17 |
| **Issue** | `GOOGLE_API_KEY=AQ.Ab8RN6LT2EYl24bafN7obvvw-vPHt6hnCnNF3f4qXTfqbPBJRQ` — live Google AI API key in plaintext. |
| **Impact** | Key compromise leads to unauthorized LLM API usage, potential billing exposure ($). |
| **Fix Applied** | None (cannot revoke third-party keys in this session). Created `.gitignore` to prevent accidental commit. |
| **Residual Risk** | **CRITICAL** — revoke key and use secrets manager. |

#### C-03: Container Runs as Root

| Field | Value |
|-------|-------|
| **Location** | `Dockerfile` |
| **Issue** | No `USER` directive — container processes run as root. If container is compromised via sandbox or plugin, attacker gains root on the container. |
| **Impact** | Full container compromise → host escape via mounted volumes. |
| **Fix Applied** | Added `adduser` + `USER appuser` to Dockerfile. |
| **Residual Risk** | **LOW** — fix has been applied and verified. |

---

### HIGH (2 open, 2 fixed)

#### H-01: CORS Misconfiguration

| Field | Value |
|-------|-------|
| **Location** | `backend/main.py` lines 172-176 |
| **Issue** | `allow_origins=["*"]` with `allow_credentials=True` — invalid per CORS spec, allows any website to interact. |
| **Impact** | Cross-origin attacks, credential theft via browser side-channel. |
| **Fix Applied** | Removed `allow_credentials=True`. |
| **Residual Risk** | **LOW** — fix validated. In production, replace `["*"]` with specific origins. |

#### H-02: File Upload — No Size Limit, No Filename Sanitization

| Field | Value |
|-------|-------|
| **Location** | `backend/main.py` — `/rag/upload` (line 1396) |
| **Issue** | `await file.read()` with no max_size, `file.filename` used directly. 50 MB files can OOM the server. |
| **Impact** | DoS via OOM, path traversal via crafted filenames (`../../etc/passwd`). |
| **Fix Applied** | Added 50 MB max_size check, `Path(filename).name` sanitization, UUID fallback for null names. |
| **Residual Risk** | **LOW** — fix validated. |

#### H-03: ZIP Extraction — Zip Slip Vulnerability (FIXED)

| Field | Value |
|-------|-------|
| **Location** | `backend/main.py` line 844-845 |
| **Issue** | `ZipFile.extractall(BASE_DIR)` without member path validation. |
| **Impact** | Crafted ZIP with `../` paths overwrites arbitrary files on the filesystem. |
| **Fix Applied** | Added per-member path validation: each extracted path must resolve within `job_dir`. Changed extractall target from `BASE_DIR` to `job_dir`. |
| **Residual Risk** | **LOW** — fix validated. |

#### H-04: Weak Path Traversal Checks (FIXED)

| Field | Value |
|-------|-------|
| **Location** | `backend/main.py` — 5 endpoints using `str(target).startswith(str(base))` |
| **Issue** | String prefix check is bypassable via symlinks, trailing character tricks. |
| **Impact** | Path traversal to read/write/delete arbitrary files. |
| **Fix Applied** | Replaced with `Path.relative_to()` which raises `ValueError` on escape. Added `_resolve_job_path()` and `_validate_file_path()` utility functions. Applied to `/regenerate-file`, `/read-project-file`, `/workspace/*/files/*` (3 endpoints), `/iterate/`, `autofix_service.py`, `autonomous_service.py`, `file_service.py`. |
| **Residual Risk** | **LOW** — fix validated. |

#### H-05: LLM Agent Execution — No Auth (MANUAL REVIEW REQUIRED)

| Field | Value |
|-------|-------|
| **Location** | `backend/main.py` — `/supervisor/run-agent/{agent_name}` |
| **Issue** | Unauthenticated. Any agent can be invoked by name. Delegates to full agent pipeline including code generation. |
| **Impact** | Arbitrary code execution, resource consumption, lateral movement. |
| **Fix Applied** | None — requires auth middleware. |
| **Residual Risk** | **HIGH** — mitigated only by network segmentation. |

---

### MEDIUM (17 total)

| ID | Issue | Location | Impact | Fix Applied | Residual Risk |
|----|-------|----------|--------|-------------|---------------|
| M-01 | No `.gitignore` in root | Root | `.env` with API key could be committed | Created `.gitignore` with secrets, cache, data dirs | **LOW** |
| M-02 | GitHub tokens in plaintext SQLite | `database/memory_store.py` line 118 | Stolen DB exposes all GitHub PATs | None — requires encryption at rest | **MEDIUM** |
| M-03 | Token embedded in clone URL | `services/github_service.py` line 449 | Token leaked via `ps aux`, error msgs, git remote | None — use credential helper | **MEDIUM** |
| M-04 | Token returned in API responses | `services/github_service.py` line 37 | Token exposed in HTTP response | None — mask in response | **MEDIUM** |
| M-05 | Undocumented env vars (26) | Across 15 files | Configuration drift, missed security settings | None — `.env.example` needs update | **LOW** |
| M-06 | Overly permissive dep ranges | `requirements.txt` | All use `>=` with no upper cap | None — pin to `~=` | **LOW** |
| M-07 | Unused deps (pydantic-settings, aiofiles, pytest-asyncio, pyflakes) | `requirements.txt` | Bloat, attack surface | None — remove unused deps | **LOW** |
| M-08 | Docker `--reload` in compose (FIXED) | `docker-compose.yml` line 14 | Dev feature in production config | Removed `--reload` flag | **LOW** |
| M-09 | Docker ports on all interfaces (FIXED) | `docker-compose.yml` line 16 | Backend exposed to network | Changed to `127.0.0.1:8000:8000` | **LOW** |
| M-10 | Docker — no healthcheck on backend (FIXED) | `docker-compose.yml` | Orchestrator can't detect failures | Added HTTP healthcheck on `/health` | **LOW** |
| M-11 | Docker — no healthcheck condition (FIXED) | `docker-compose.yml` line 40 | Frontend starts before backend ready | Changed to `condition: service_healthy` | **LOW** |
| M-12 | Dynamic SQL column names | `database/memory_store.py` lines 2796, 2927 | Limited injection via f-string column names | None — whitelist exists but f-string bypasses `?` | **LOW** |
| M-13 | `start.bat` kills ALL Python processes (FIXED) | `start.bat` line 4 | Terminates other running Python apps | Changed to target only uvicorn/streamlit PIDs | **LOW** |
| M-14 | No rate limiting on any endpoint | `backend/main.py` | DoS via campaign run, sandbox exec, project gen | None — needs rate limiting middleware | **MEDIUM** |
| M-15 | No request body size limits | `backend/main.py` | Large payloads exhaust memory | None — add `max_request_size` | **MEDIUM** |
| M-16 | Browser service uploads any file | `services/browser_service.py` line 167 | Any server file can be uploaded to remote sites via browser | None — needs allowed paths | **MEDIUM** |
| M-17 | LLM result logged (500 chars) | `backend/main.py` line 881 | If prompt/code contains secrets, they go to logs | None — add redaction | **LOW** |

---

### LOW (16 total)

| ID | Issue | Location | Residual Risk |
|----|-------|----------|---------------|
| L-01 | Missing `--no-cache-dir` in generated Dockerfiles | `generated_projects/*/Dockerfile` | Slightly larger images |
| L-02 | Image not pinned to digest | `Dockerfile` line 2 | Non-reproducible builds |
| L-03 | `curl` installed at runtime | `Dockerfile` line 10 | Additional attack surface |
| L-04 | No `CMD` in Dockerfile | `Dockerfile` (no CMD/ENTRYPOINT) | Container doesn't start by itself |
| L-05 | Ollama image uses `:latest` tag | `docker-compose.yml` line 3 | Unpredictable updates |
| L-06 | No Docker secrets management | `docker-compose.yml` | Secrets passed via .env file |
| L-07 | Unlocked reads on shared state | `services/process_manager.py` line 272 | Stale reads under concurrent access |
| L-08 | Unlocked reads on shared state | `services/runtime_orchestrator.py` line 215 | Stale reads under concurrent access |
| L-09 | Unlocked reads on shared state | `services/session_manager.py` line 104 | Stale reads under concurrent access |
| L-10 | Concurrent file writes | `agents/code_agent.py` line 287 | Race condition on file writes |
| L-11 | Scheduler thread race | `services/evaluation_scheduler.py` line 408 | Shared dict mutation without lock |
| L-12 | Unbounded loop in session execute_all | `services/session_manager.py` line 189 | Potential infinite loop |
| L-13 | High default pagination (500) | `database/memory_store.py` line 2880 | Memory pressure on large datasets |
| L-14 | Webhook receiver with empty token | `backend/main.py` line 2014 | Unvalidated webhook events |
| L-15 | Marketplace `source_url` used as path | `services/marketplace_service.py` line 212 | `shutil.rmtree()` on user-supplied path |
| L-16 | Plugin source path for `shutil.rmtree()` | `services/plugin_registry.py` line 252 | User-supplied path deleted |

---

## Files Modified

| File | Changes |
|------|---------|
| `backend/main.py` | Added `_resolve_job_path()`, `_validate_file_path()`; fixed path checks in 7 endpoints; fixed CORS; fixed ZIP slip; fixed rag/upload size/filename; added path validation in iterate |
| `services/file_service.py` | Added `_resolve_path()` with path traversal validation; all functions now validate via `relative_to()` |
| `services/autofix_service.py` | Added path traversal validation to LLM-parsed file paths |
| `services/autonomous_service.py` | Added path traversal validation to LLM-parsed file paths |
| `Dockerfile` | Added `adduser` + `USER appuser` (non-root) |
| `docker-compose.yml` | Removed `--reload`; added healthchecks; restricted ports to 127.0.0.1; added `condition: service_healthy` |
| `start.bat` | Fixed `taskkill` to target only uvicorn/streamlit processes |
| `.gitignore` | Created with secrets, cache, data directories |

## Files Requiring Manual Review

| File | Reason |
|------|--------|
| `backend/main.py` | Add authentication middleware (API key via header) |
| `.env` | Revoke and rotate `GOOGLE_API_KEY` |
| `database/memory_store.py` | Encrypt GitHub tokens at rest |
| `services/github_service.py` | Use credential helper instead of embedding tokens in URLs |
| `requirements.txt` | Pin dependencies with `~=`; remove unused packages |
| `services/browser_service.py` | Restrict accessible file paths |
| `services/marketplace_service.py` | Validate paths before `shutil.rmtree()` |
| `services/plugin_registry.py` | Validate paths before `shutil.rmtree()` |

---

## Vulnerabilities Fixed (12)

1. CORS misconfiguration (removed `allow_credentials=True`)
2. File upload — added 50 MB max size + sanitized filename
3. ZIP slip — per-member path validation + restricted extraction to job_dir
4. Weak path traversal checks — replaced `startswith` with `relative_to()`
5. LLM-parsed file paths — added validation in iterate, autofix, autonomous
6. `file_service.py` — added path validation across all functions
7. Docker container runs as root — added `USER appuser`
8. Docker `--reload` in production — removed
9. Docker ports on all interfaces — restricted to 127.0.0.1
10. Docker missing healthchecks — added for backend + frontend dependency
11. `start.bat` — fixed broad `taskkill /f /im python.exe`
12. Root `.gitignore` — created to protect `.env` and other artifacts

---

## Remaining Risks

1. **No authentication** — every endpoint is open (most critical unfixed issue)
2. **Real API key in .env** — must be revoked and rotated
3. **GitHub tokens in plaintext** — stored in SQLite, embedded in clone URLs
4. **No rate limiting** — DoS via campaign/sandbox/project generation endpoints
5. **No request size limits** — memory exhaustion via large payloads
6. **26 undocumented environment variables** — configuration management gap
7. **Unused dependencies (4)** — attack surface bloat
8. **Unlocked shared state (3 locations)** — race conditions under concurrent access

---

## Release Readiness Recommendation

**Status: NOT RELEASE READY**

The project **cannot** ship as v13.0.0 until:

1. **Critical findings = 0** (currently 3 open: no auth, API key in .env, root container)
2. **High findings ≤ 3** (currently 2 open: CORS, LLM agent execution)

**Minimum requirements for release gate:**
- [x] CORS fixed (DONE)
- [x] ZIP slip fixed (DONE)
- [x] File upload restrictions added (DONE)
- [x] Path traversal checks hardened (DONE)
- [x] Docker non-root user added (DONE)
- [x] `.gitignore` created (DONE)
- [ ] Add authentication middleware to all endpoints
- [ ] Revoke/rotate `GOOGLE_API_KEY` in `.env`
- [ ] Encrypt GitHub tokens at rest
- [ ] Add rate limiting middleware
- [ ] Add request body size limits

**Recommended priority order:**
1. Auth middleware (API key via header, checked by `Depends()`)
2. Revoke hardcoded API key, use secrets manager
3. Encrypt GitHub tokens (AES-256-GCM or similar)
4. Rate limiting middleware
5. Request body size limits
6. Pin dependencies, remove unused packages
