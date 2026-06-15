"""
Cleanup Service — removes generated project ZIPs older than RETENTION_HOURS.

New in v4. Called from a background daemon thread started at app startup.
Configurable via env var ZIP_RETENTION_HOURS (default: 24).
"""
import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(os.getenv("GENERATED_PROJECTS_DIR", "./generated_projects"))
RETENTION_HOURS: int = int(os.getenv("ZIP_RETENTION_HOURS", "24"))
CHECK_INTERVAL_SECONDS: int = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "3600"))  # every hour


def _run_cleanup() -> int:
    """Delete ZIPs older than RETENTION_HOURS. Returns number of files deleted."""
    if not BASE_DIR.exists():
        return 0
    cutoff = time.time() - RETENTION_HOURS * 3600
    deleted = 0
    for zip_file in BASE_DIR.glob("*.zip"):
        try:
            if zip_file.stat().st_mtime < cutoff:
                zip_file.unlink()
                deleted += 1
                logger.info("Cleanup: deleted %s", zip_file.name)
        except Exception as exc:
            logger.warning("Cleanup: could not delete %s: %s", zip_file.name, exc)
    return deleted


def _cleanup_loop() -> None:
    """Daemon loop — runs cleanup every CHECK_INTERVAL_SECONDS."""
    logger.info(
        "Cleanup service started — retention=%dh, interval=%ds",
        RETENTION_HOURS, CHECK_INTERVAL_SECONDS,
    )
    while True:
        try:
            deleted = _run_cleanup()
            if deleted:
                logger.info("Cleanup: removed %d old ZIP(s).", deleted)
        except Exception as exc:
            logger.error("Cleanup loop error: %s", exc)
        time.sleep(CHECK_INTERVAL_SECONDS)


def start_cleanup_daemon() -> threading.Thread:
    """Start the cleanup loop as a daemon thread. Call once at app startup."""
    t = threading.Thread(target=_cleanup_loop, daemon=True, name="cleanup-daemon")
    t.start()
    return t


def run_once() -> int:
    """Run a single cleanup pass (useful for testing)."""
    return _run_cleanup()
