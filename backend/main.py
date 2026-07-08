"""ProjectPilot — FastAPI Backend

Refactored: API endpoint handlers extracted into modular FastAPI routers under backend/routes/.
Keeps only server initialization, middleware configuration, and lifespan context manager.
"""

import asyncio
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from database.chroma_db import init_db, set_workspace_context
from database.database import init_db as init_sqlalchemy_db
from database.memory_store import init_db as init_memory_db
from services.activity_service import init_activity_db
from services.audit_service import init_audit_db
from services.auth_service import Role, lookup_role
from services.cleanup_service import start_cleanup_daemon
from services.jwt_service import decode_access_token
from services.llm_service import ensure_models, is_available
from services.notification_service import init_notifications_db
from services.rate_limiter import RateLimitMiddleware

# ── Route imports ─────────────────────────────────────────────────────────
from backend.routes.auth_routes import router as auth_router, router_workspace as workspace_router
from backend.routes.health_routes import router as health_router
from backend.routes.rag_routes import router as rag_router
from backend.routes.analytics_routes import router as analytics_router
from backend.routes.plugin_routes import router as plugin_router
from backend.routes.diagram_routes import router as diagram_router
from backend.routes.supervisor_routes import router as supervisor_router
from backend.routes.pipeline_routes import router as pipeline_router
from backend.routes.github_routes import router as github_router
from backend.routes.chat_routes import router as chat_router
from backend.routes.workspace_routes import router as workspace_file_router
from backend.routes.browser_routes import router as browser_router
from backend.routes.repo_routes import router as repo_router
from backend.routes.dashboard_routes import router as dashboard_router
from backend.routes.docs_routes import router as docs_router
from backend.routes.graph_routes import router as graph_router
from backend.routes.kg_routes import router as kg_router
from backend.routes.debate_routes import router as debate_router
from backend.routes.validation_routes import router as validation_router
from backend.routes.autonomous_routes import router as autonomous_router
from backend.routes.runtime_routes import router as runtime_router
from backend.routes.container_routes import router as container_router
from backend.routes.process_routes import router as process_router
from backend.routes.healing_routes import router as healing_router
from backend.routes.deployment_routes import router as deployment_router
from backend.routes.monitor_routes import router as monitor_router
from backend.routes.sdlc_routes import router as sdlc_router
from backend.routes.session_routes import router as session_router
from backend.routes.learning_routes import router as learning_router
from backend.routes.benchmark_routes import router as benchmark_router
from backend.routes.org_routes import router as org_router
from backend.routes.evaluation_routes import router as evaluation_router
from backend.routes.campaign_routes import router as campaign_router
from backend.routes.autofix_routes import router as autofix_router

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)s}',
)
logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)

# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_memory_db()
    init_sqlalchemy_db()
    init_audit_db()
    init_activity_db()
    init_notifications_db()
    logger.info('{"event":"db_ready","store":"chromadb+sqlite+sqlalchemy"}')

    if os.getenv("ADMIN_API_KEY"):
        logger.info('{"event":"auth_configured","mode":"admin_api_key"}')
    else:
        logger.warning(
            '{"event":"auth_ephemeral","detail":"ADMIN_API_KEY not set. Using ephemeral key printed at startup."}'
        )

    if os.getenv("GOOGLE_API_KEY"):
        logger.info('{"event":"cloud_api_key_configured","provider":"google"}')
    else:
        logger.info(
            '{"event":"cloud_api_key_missing","detail":"Cloud LLM calls will fail until GOOGLE_API_KEY is set."}'
        )

    loop = asyncio.get_event_loop()
    loop.run_in_executor(_executor, _wait_and_pull_models)
    start_cleanup_daemon()
    _init_supervisor()
    _init_evaluation()
    logger.info('{"event":"startup_complete","version":"13.0.0"}')
    yield
    logger.info('{"event":"shutdown"}')


def _init_supervisor():
    import agents.code_agent
    import agents.debug_agent
    import agents.docs_agent
    import agents.planner_agent
    import agents.requirement_agent
    import agents.security_agent
    import agents.test_gen_agent
    import agents.validation_agent
    from services.supervisor_service import AgentPriority, Supervisor

    s = Supervisor()

    def _wrap(fn, arg_names):
        def wrapper(context):
            kwargs = {k: context[k] for k in arg_names if k in context}
            return fn(**kwargs)

        return wrapper

    s.register_agent(
        "RequirementAgent",
        _wrap(agents.requirement_agent.run, ["prompt", "project_name", "job_id", "model", "stack"]),
        priority=AgentPriority.CRITICAL,
        team="pipeline",
    )
    s.register_agent(
        "PlannerAgent",
        _wrap(agents.planner_agent.run, ["requirements", "job_id", "model"]),
        priority=AgentPriority.HIGH,
        team="pipeline",
    )
    s.register_agent(
        "CodeAgent",
        _wrap(agents.code_agent.run, ["requirements", "blueprint", "job_id", "model"]),
        priority=AgentPriority.HIGH,
        team="pipeline",
    )
    s.register_agent(
        "TestGenAgent",
        _wrap(agents.test_gen_agent.run, ["generated_files", "requirements", "blueprint", "job_id", "model"]),
        priority=AgentPriority.NORMAL,
        team="pipeline",
    )
    s.register_agent(
        "DebugAgent",
        _wrap(agents.debug_agent.run, ["generated_files", "job_id", "model", "blueprint"]),
        priority=AgentPriority.NORMAL,
        team="pipeline",
    )
    s.register_agent(
        "DocsAgent",
        _wrap(agents.docs_agent.run, ["requirements", "blueprint", "generated_files", "job_id", "model"]),
        priority=AgentPriority.LOW,
        team="pipeline",
    )
    s.register_agent(
        "ValidationAgent",
        _wrap(agents.validation_agent.run, ["job_id", "requirements", "blueprint"]),
        priority=AgentPriority.LOW,
        team="pipeline",
    )
    s.register_agent(
        "SecurityAgent",
        _wrap(agents.security_agent.run, ["generated_files", "job_id", "blueprint", "model"]),
        priority=AgentPriority.LOW,
        team="quality",
    )
    logger.info('{"event":"supervisor_ready","agents":8}')


app = FastAPI(
    title="ProjectPilot",
    description="Autonomous engineering platform — Plugin & Agent SDK Ecosystem",
    version="13.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

# ── Include all routers ──────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(workspace_router)
app.include_router(health_router)
app.include_router(rag_router)
app.include_router(analytics_router)
app.include_router(plugin_router)
app.include_router(diagram_router)
app.include_router(supervisor_router)
app.include_router(pipeline_router)
app.include_router(github_router)
app.include_router(chat_router)
app.include_router(workspace_file_router)
app.include_router(browser_router)
app.include_router(repo_router)
app.include_router(dashboard_router)
app.include_router(docs_router)
app.include_router(graph_router)
app.include_router(kg_router)
app.include_router(debate_router)
app.include_router(validation_router)
app.include_router(autonomous_router)
app.include_router(runtime_router)
app.include_router(container_router)
app.include_router(process_router)
app.include_router(healing_router)
app.include_router(deployment_router)
app.include_router(monitor_router)
app.include_router(sdlc_router)
app.include_router(session_router)
app.include_router(learning_router)
app.include_router(benchmark_router)
app.include_router(org_router)
app.include_router(evaluation_router)
app.include_router(campaign_router)
app.include_router(autofix_router)

MAX_BODY_SIZE = int(os.getenv("MAX_REQUEST_BODY_SIZE", "10_485_760"))


@app.middleware("http")
async def limit_request_body(request: Request, call_next):
    if request.method in ("POST", "PUT", "PATCH"):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_BODY_SIZE:
            return JSONResponse(
                status_code=413,
                content={"detail": f"Request body too large (max {MAX_BODY_SIZE // 1024 // 1024} MB)."},
            )
    return await call_next(request)


PROTECTED_PREFIXES = [
    "/workspace/",
    "/jobs",
    "/regenerate-file",
    "/iterate/",
    "/validate/",
    "/deploy/",
    "/plugins/",
    "/marketplace/",
    "/agents/",
    "/workflows/",
    "/organization/",
    "/github/",
    "/sandbox/",
    "/supervisor/",
    "/autonomous/",
    "/debate/",
    "/evaluation/",
    "/benchmarks/",
    "/benchmark/",
    "/campaign/",
    "/rag/",
    "/chat/",
    "/browser/",
    "/runtime/",
    "/process/",
    "/api/workspace/",
    "/api/workspace",
    "/analytics/",
]

ADMIN_ONLY_PREFIXES = [
    "/supervisor/",
    "/sandbox/",
    "/process/",
    "/plugins/install",
    "/plugins/uninstall",
    "/marketplace/install",
    "/marketplace/delete",
]

SKIP_AUTH = os.getenv("SKIP_AUTH", "").lower() in ("true", "1", "yes")


@app.middleware("http")
async def authenticate_request(request: Request, call_next):
    if SKIP_AUTH:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            jwt_payload = decode_access_token(auth_header[7:])
            if jwt_payload:
                request.state.user_id = jwt_payload.get("sub")
                request.state.workspace_id = jwt_payload.get("ws", "")
                set_workspace_context(request.state.workspace_id)
        return await call_next(request)

    path = request.url.path

    if path in ("/docs", "/openapi.json", "/health") or path.startswith("/api/auth/"):
        return await call_next(request)

    needs_auth = any(path.startswith(p) for p in PROTECTED_PREFIXES)
    needs_admin = any(path.startswith(p) for p in ADMIN_ONLY_PREFIXES)

    if needs_auth or needs_admin:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Missing or invalid Authorization header. Use: Bearer <token>"},
            )

        token = auth_header[7:]

        jwt_payload = decode_access_token(token)
        if jwt_payload:
            request.state.user_id = jwt_payload.get("sub")
            request.state.workspace_id = jwt_payload.get("ws", "")
            set_workspace_context(request.state.workspace_id)
            return await call_next(request)

        role = lookup_role(token)

        if needs_admin and role != Role.ADMIN:
            return JSONResponse(status_code=403, content={"detail": "Admin access required."})
        if needs_auth and role == Role.NONE:
            return JSONResponse(status_code=401, content={"detail": "Invalid or expired token."})

    return await call_next(request)


def _wait_and_pull_models() -> None:
    if os.environ.get("SKIP_AUTH") == "true":
        logger.info('{"event":"ollama_skip_wait","reason":"test_mode"}')
        return

    for attempt in range(40):
        if is_available():
            logger.info('{"event":"ollama_ready","pulling_models":true}')
            ensure_models()
            return
        logger.info('{"event":"ollama_wait","attempt":%d}', attempt + 1)
        time.sleep(5)
    logger.error('{"event":"ollama_unavailable"}')


# ===================== v12 — Continuous Autonomous Evaluation =====================


def _init_evaluation():
    """Register evaluation completion handler, recover state, check missed runs."""
    from services.evaluation_reporter import get_evaluation_reporter
    from services.evaluation_scheduler import get_evaluation_scheduler

    scheduler = get_evaluation_scheduler()

    recovery = scheduler.recover_state()
    if recovery.get("marked_stale", 0) > 0:
        logger.info("Recovery marked %d stale evaluation runs", recovery["marked_stale"])
    missed = scheduler.check_missed_runs()
    if missed:
        logger.info("Recovery triggered %d missed evaluation runs", len(missed))

    def _on_run_completed(run):
        run_dict = run.to_dict()
        from database.memory_store import mem_save_evaluation_run, mem_save_evaluation_report

        db_run = {
            "id": run_dict["id"],
            "trigger_type": run_dict.get("schedule", "on_demand"),
            "status": run_dict.get("status", ""),
            "autonomy_score": run_dict.get("autonomy_score", 0.0),
            "success_rate": run_dict.get("success_rate", 0.0),
            "total_cost": run_dict.get("total_cost", 0.0),
            "total_runtime": run_dict.get("avg_runtime_ms", 0.0),
            "healing_rate": run_dict.get("healing_rate", 0.0),
            "deployment_success_rate": run_dict.get("deployment_success_rate", 0.0),
            "benchmark_score": run_dict.get("autonomy_score", 0.0),
            "tasks_completed": 0,
            "tasks_failed": 0,
            "error_log": run_dict.get("error", ""),
            "started_at": run_dict.get("started_at"),
            "completed_at": run_dict.get("completed_at"),
            "created_at": run_dict.get("completed_at"),
        }
        mem_save_evaluation_run(db_run)

        if run.schedule in ("nightly", "weekly", "release"):
            report_type = "daily" if run.schedule == "nightly" else run.schedule
            past_runs = [r.to_dict() for r in scheduler.list_runs(status="completed")]
            reporter = get_evaluation_reporter()
            report = reporter.generate_report(report_type=report_type, runs=past_runs)
            report_dict = report.to_dict()
            db_report = {
                "id": report_dict["id"],
                "report_type": report_dict["report_type"],
                "title": report_dict["title"],
                "summary": report_dict["summary"],
                "metrics": report_dict.get("metrics", {}),
                "trends": {"trend_analysis": report_dict.get("trend_analysis", "")},
                "regressions_found": report_dict.get("regressions", []),
                "improvements_found": report_dict.get("improvements", []),
                "recommendations": report_dict.get("recommendations", []),
                "report_markdown": report_dict.get("markdown", ""),
                "period_start": report_dict.get("period_start"),
                "period_end": report_dict.get("period_end"),
                "created_at": report_dict.get("generated_at"),
            }
            mem_save_evaluation_report(db_report)

        try:
            from services.learning_feedback_service import get_learning_feedback_service

            learning = get_learning_feedback_service()
            learning.ingest_evaluation_result(run_dict)
            if run.schedule in ("nightly", "weekly", "release"):
                learning.generate_recommendations()
        except Exception as e:
            logger.warning("Learning feedback ingestion failed: %s", e)

    scheduler.register_handler("evaluation_completion", _on_run_completed)