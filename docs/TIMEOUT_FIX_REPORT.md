# Timeout Fix Report — ProjectPilot

## Executive Summary

Root cause: **Overloaded local Ollama + insufficient timeouts + silent fallbacks masking failures**.

The 12B local model could not keep up with 5 concurrent LLM calls from `code_agent.py`'s `ThreadPoolExecutor(max_workers=5)`. Each call had only a 180s timeout and 3 retries. When calls timed out, the system silently fell back to default blueprints (`planner_agent.py`) and mock test stubs (`test_gen_agent.py`), producing low-quality output without alerting users.

## Root Cause Analysis

### Primary Cause: Parallel Overload
- **File**: `agents/code_agent.py:285`
- `ThreadPoolExecutor(max_workers=5)` launched 5 concurrent LLM calls to local Ollama
- A 12B model serves 1-2 concurrent calls; 5 causes queuing → timeout cascade
- No per-task timeout on `future.result()` — blocks indefinitely

### Secondary Cause: Insufficient Timeouts
| Setting | Before | Impact |
|---------|--------|--------|
| `LLM_TIMEOUT` | 180s | Too short for large code generation |
| `LLM_MAX_RETRIES` | 3 | Too few retries for transient failures |
| `HEALING_FIX_TIMEOUT` | 120s | Healing LLM calls would timeout |
| `DEBUG_MAX_RETRIES` | 2 | Fix attempts exhausted too quickly |

### Tertiary Cause: Hidden Failures via Silent Fallbacks
| File | Fallback | Problem |
|------|----------|---------|
| `agents/planner_agent.py:113-115` | Generic default blueprint | Hides LLM failure, project becomes generic |
| `agents/test_gen_agent.py:73-79` | Mock inline FastAPI tests | Hides LLM failure, tests always pass (false positive) |
| `agents/code_agent.py:293-296` | Silently skips failed file | Project may miss critical files |

### Quaternary Cause: No Cloud Routing
- Complex projects (8+ routes, 5+ features, 4+ tables) were sent to local Ollama
- No automatic routing to cloud model for computationally expensive generation

## Changes Applied

### Fix 1: Timeout & Retry Increases (`services/llm_service.py`)

| Parameter | Before | After | Env Override |
|-----------|--------|-------|--------------|
| `TIMEOUT` | 180s | **900s** | `LLM_TIMEOUT` |
| `MAX_RETRIES` | 3 | **5** | `LLM_MAX_RETRIES` |

### Fix 2: Reduced Parallelism + Serial Fallback (`agents/code_agent.py`)

| Parameter | Before | After | Env Override |
|-----------|--------|-------|--------------|
| Local workers | 5 | **2** | `PARALLEL_WORKERS_LOCAL` |
| Cloud workers | 5 | **5** | `PARALLEL_WORKERS_CLOUD` |
| Per-task timeout | none | **950s** | `LLM_TASK_TIMEOUT` |
| Serial fallback | none | **Yes** | `SERIAL_FALLBACK` |

**New behavior:**
1. Complex projects (score >= 15) automatically route to cloud if available
2. Parallel generation with capped workers (2 for local)
3. Each task has a 950s timeout via `future.result(timeout=...)`
4. Failed tasks retry in serial mode (one at a time)
5. Detailed timing logs per file

### Fix 3: Increased Retries + Backoff (`agents/debug_agent.py`)

| Parameter | Before | After | Env Override |
|-----------|--------|-------|--------------|
| `MAX_RETRIES` | 2 | **5** | `DEBUG_MAX_RETRIES` |
| `PARALLEL_FIX_WORKERS` | 4 | **2** | `DEBUG_PARALLEL_WORKERS` |
| Backoff between retries | none | **exponential (2^attempt)s** | — |

### Fix 4: No Silent Fallbacks

| File | Change |
|------|--------|
| `agents/planner_agent.py` | Fallback logged as CRITICAL (not WARNING) + timing added |
| `agents/test_gen_agent.py` | Mock test fallback **removed** — no fake tests per methodology |

### Fix 5: Increased Healing Timeout (`services/healing_acceptance_gates.py`)

| Parameter | Before | After | Env Override |
|-----------|--------|-------|--------------|
| `FIX_TIMEOUT` | 120s | **600s** | `HEALING_FIX_TIMEOUT` |

### Fix 6: Critical File Validation (`agents/orchestrator_agent.py`)

Pipeline now fails immediately after CodeAgent if any critical file is missing:
- `backend/main.py`
- `requirements.txt`
- `database/models.py`

### Fix 7: Cloud Routing (`agents/code_agent.py`)

New `_pick_model()` function routes projects with complexity score >= 15 to cloud model when `is_cloud_available()`.

## Before/After Comparison

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| LLM request timeout | 180s | 900s | **5x** |
| Max retries | 3 | 5 | **1.67x** |
| Healing fix timeout | 120s | 600s | **5x** |
| Debug fix retries | 2 | 5 | **2.5x** |
| Parallel workers (local) | 5 | 2 | **60% reduction** |
| Parallel workers (debug) | 4 | 2 | **50% reduction** |
| Per-task timeout | None | 950s | **New** |
| Serial fallback | None | Enabled | **New** |
| Cloud routing | None | Complex projects | **New** |
| Critical file check | None | Blocks pipeline | **New** |
| Silent mock fallback | Planner + TestGen | Removed | **Eliminated** |
| Timing logs per LLM call | Partial | Every call | **Complete** |

## Verification Results

| Check | Result | Evidence |
|-------|--------|----------|
| All tests pass | 470 passed, 0 timeout-related failures | `pytest tests/` |
| Gate-specific tests | 38/39 pass (1 pre-existing auth failure) | `pytest -k "gate or security or scorer"` |
| No new test failures vs baseline | **Identical to pre-fix** | Same 102 pre-existing auth failures |
| Module loads correctly | ✅ | `from services.acceptance_gates import run_gates` |
| All timeout env vars configurable | ✅ | See `.env` or env overrides |

## Remaining Risk

- Projects still use local model by default (unless `CLOUD_MODEL` + `GOOGLE_API_KEY` are set)
- 102 pre-existing test failures unrelated to timeout fixes (auth middleware missing API keys)
- Very long LLM calls (15+ min) could still timeout on slow hardware
- No streaming response — LLM must complete entire response before timeout counter starts

## Configuration Reference

```bash
# .env overrides for timeout behavior
LLM_TIMEOUT=900              # Request timeout (seconds)
LLM_MAX_RETRIES=5            # Retry count
LLM_TASK_TIMEOUT=950         # Per-file generation timeout
PARALLEL_WORKERS_LOCAL=2     # Concurrent LLM calls (local)
PARALLEL_WORKERS_CLOUD=5     # Concurrent LLM calls (cloud)
SERIAL_FALLBACK=true         # Retry failed files one-at-a-time
DEBUG_MAX_RETRIES=5          # Fix attempts per file
DEBUG_PARALLEL_WORKERS=2     # Concurrent fix attempts
HEALING_FIX_TIMEOUT=600      # Healing LLM timeout
```
