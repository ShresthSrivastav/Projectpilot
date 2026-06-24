"""Platform reset — clears runtime/history data while preserving schemas, config, and source code.

Usage:
    python scripts/reset_platform.py              # clear all (interactive prompt)
    python scripts/reset_platform.py --force       # clear all (non-interactive)
    python scripts/reset_platform.py --jobs        # only clear jobs
    python scripts/reset_platform.py --evaluations # only clear evaluations
    python scripts/reset_platform.py --benchmarks  # only clear benchmark results
    python scripts/reset_platform.py --learning    # only clear learning data
    python scripts/reset_platform.py --campaigns   # only clear campaign data
    python scripts/reset_platform.py --projects    # only clear generated projects
    python scripts/reset_platform.py --artifacts   # only clear build artifacts
    python scripts/reset_platform.py --logs        # only clear log files
"""

import argparse
import logging
import shutil
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("reset_platform")

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIRS = {
    "chroma_data": BASE_DIR / "chroma_data",
    "chroma_db_v4": BASE_DIR / "chroma_db_v4",
    "test_chroma_data_v4": BASE_DIR / "test_chroma_data_v4",
    "evaluation_data": BASE_DIR / "evaluation_data",
    "benchmark_campaign": BASE_DIR / "benchmark_campaign",
    "benchmark_history": BASE_DIR / "benchmark_history",
    "validation_artifacts": BASE_DIR / "validation_artifacts",
    "memory_store": BASE_DIR / "memory_store",
    "generated_projects": BASE_DIR / "generated_projects",
    "graph_checkpoints": BASE_DIR / "graph_checkpoints",
    "healing_data": BASE_DIR / "healing_data",
    "marketplace_data": BASE_DIR / "marketplace_data",
    "org_data": BASE_DIR / "org_data",
    "plugin_data": BASE_DIR / "plugin_data",
    "process_logs": BASE_DIR / "process_logs",
    "runtime_data": BASE_DIR / "runtime_data",
    "autonomous_data": BASE_DIR / "autonomous_data",
}

LOG_FILES = [
    "backend_err.log",
    "backend_out.log",
    "frontend_err.log",
    "frontend_out.log",
    "stderr.log",
    "v5_stderr.log",
    "v5_stdout.log",
    "test_output.log",
]


def confirm(prompt: str) -> bool:
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer in ("y", "yes")


def _rmtree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
        logger.info("  Removed: %s", path)


def _rmfile(path: Path) -> None:
    if path.exists():
        path.unlink()
        logger.info("  Removed: %s", path)


def clear_jobs() -> None:
    logger.info("Clearing job database...")
    mem_db = DATA_DIRS["memory_store"] / "autodev_memory.db"
    if mem_db.exists():
        conn = sqlite3.connect(str(mem_db))
        cur = conn.cursor()
        tables = [
            "projects",
            "project_analytics",
            "insights",
            "chat_conversations",
            "chat_messages",
            "organizations",
            "repositories",
            "repository_relationships",
            "cross_repo_changes",
            "impact_reports",
            "plugins",
            "marketplace_packages",
            "custom_agents",
            "custom_workflows",
            "evaluation_runs",
            "evaluation_reports",
            "regressions",
            "version_comparisons",
            "learning_feedback",
            "learning_patterns",
            "learning_recommendations",
            "iteration_history",
            "cost_logs",
            "graph_sessions",
            "schedule_metadata",
        ]
        for table in tables:
            try:
                cur.execute(f"DELETE FROM {table}")
                logger.info("  Cleared table: %s", table)
            except sqlite3.OperationalError:
                pass
        conn.commit()
        conn.close()
        logger.info("  Memory DB tables cleared.")

    chroma_db = DATA_DIRS["chroma_data"]
    if chroma_db.exists():
        for item in chroma_db.iterdir():
            if item.is_dir():
                _rmtree(item)
            else:
                _rmfile(item)
        logger.info("  ChromaDB data cleared.")

    # chroma_db_v4 (stale copy)
    _rmtree(DATA_DIRS["chroma_db_v4"])
    _rmtree(DATA_DIRS["test_chroma_data_v4"])


def clear_evaluations() -> None:
    logger.info("Clearing evaluation data...")
    _rmtree(DATA_DIRS["evaluation_data"])
    mem_db = DATA_DIRS["memory_store"] / "autodev_memory.db"
    if mem_db.exists():
        conn = sqlite3.connect(str(mem_db))
        cur = conn.cursor()
        for table in ("evaluation_runs", "evaluation_reports", "regressions", "version_comparisons"):
            try:
                cur.execute(f"DELETE FROM {table}")
                logger.info("  Cleared table: %s", table)
            except sqlite3.OperationalError:
                pass
        conn.commit()
        conn.close()


def clear_benchmarks() -> None:
    logger.info("Clearing benchmark results...")
    campaigns_dir = DATA_DIRS["benchmark_campaign"]
    if campaigns_dir.exists():
        for sub in ("results", "reports"):
            subdir = campaigns_dir / sub
            if subdir.exists():
                _rmtree(subdir)
        for p in campaigns_dir.iterdir():
            if p.suffix == ".json":
                _rmfile(p)
    _rmtree(DATA_DIRS["benchmark_history"])


def clear_learning() -> None:
    logger.info("Clearing learning data...")
    mem_db = DATA_DIRS["memory_store"] / "autodev_memory.db"
    if mem_db.exists():
        conn = sqlite3.connect(str(mem_db))
        cur = conn.cursor()
        for table in ("learning_feedback", "learning_patterns", "learning_recommendations"):
            try:
                cur.execute(f"DELETE FROM {table}")
                logger.info("  Cleared table: %s", table)
            except sqlite3.OperationalError:
                pass
        conn.commit()
        conn.close()


def clear_campaigns() -> None:
    logger.info("Clearing campaign data...")
    _rmtree(DATA_DIRS["benchmark_campaign"] / "results")
    _rmtree(DATA_DIRS["benchmark_campaign"] / "reports")


def clear_generated_projects() -> None:
    logger.info("Clearing generated projects...")
    projects_dir = DATA_DIRS["generated_projects"]
    if projects_dir.exists():
        for item in projects_dir.iterdir():
            if item.is_dir():
                _rmtree(item)
        logger.info("  Generated projects cleared.")
    _rmtree(DATA_DIRS["graph_checkpoints"])
    _rmtree(DATA_DIRS["healing_data"])
    _rmtree(DATA_DIRS["autonomous_data"])
    _rmtree(DATA_DIRS["runtime_data"])
    _rmtree(DATA_DIRS["process_logs"])


def clear_artifacts() -> None:
    logger.info("Clearing build artifacts...")
    for pattern in ("**/__pycache__", "**/.pytest_cache", "**/*.pyc", "**/*.pyo"):
        for p in BASE_DIR.glob(pattern):
            if p.is_dir():
                _rmtree(p)
            else:
                _rmfile(p)
    _rmtree(DATA_DIRS["validation_artifacts"])
    _rmtree(DATA_DIRS["marketplace_data"])
    _rmtree(DATA_DIRS["org_data"])
    _rmtree(DATA_DIRS["plugin_data"] / "installed")
    logger.info("  Artifacts cleared.")


def clear_logs() -> None:
    logger.info("Clearing log files...")
    for logfile in LOG_FILES:
        _rmfile(BASE_DIR / logfile)
    for p in BASE_DIR.glob("*.log"):
        _rmfile(p)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset ProjectPilot platform history data")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--jobs", action="store_true", help="Clear job database only")
    parser.add_argument("--evaluations", action="store_true", help="Clear evaluation data only")
    parser.add_argument("--benchmarks", action="store_true", help="Clear benchmark results only")
    parser.add_argument("--learning", action="store_true", help="Clear learning data only")
    parser.add_argument("--campaigns", action="store_true", help="Clear campaign data only")
    parser.add_argument("--projects", action="store_true", help="Clear generated projects only")
    parser.add_argument("--artifacts", action="store_true", help="Clear build artifacts only")
    parser.add_argument("--logs", action="store_true", help="Clear log files only")

    args = parser.parse_args()

    has_specific = any(
        [
            args.jobs,
            args.evaluations,
            args.benchmarks,
            args.learning,
            args.campaigns,
            args.projects,
            args.artifacts,
            args.logs,
        ]
    )

    if not has_specific:
        logger.info(
            "This will clear ALL platform history data (jobs, evaluations, benchmarks, learning, campaigns, projects, artifacts, logs)."
        )
        logger.info("The following will be PRESERVED: source code, tests, configuration, schemas.")
        if not args.force and not confirm("Proceed?"):
            logger.info("Aborted.")
            return
        clear_logs()
        clear_artifacts()
        clear_generated_projects()
        clear_campaigns()
        clear_learning()
        clear_benchmarks()
        clear_evaluations()
        clear_jobs()
    else:
        if not args.force and not confirm("Proceed with selected reset operations?"):
            logger.info("Aborted.")
            return
        if args.jobs:
            clear_jobs()
        if args.evaluations:
            clear_evaluations()
        if args.benchmarks:
            clear_benchmarks()
        if args.learning:
            clear_learning()
        if args.campaigns:
            clear_campaigns()
        if args.projects:
            clear_generated_projects()
        if args.artifacts:
            clear_artifacts()
        if args.logs:
            clear_logs()

    logger.info("Reset complete.")


if __name__ == "__main__":
    main()
