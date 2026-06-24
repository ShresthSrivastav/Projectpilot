import logging
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logger = logging.getLogger(__name__)

MEMORY_DIR = os.getenv(
    "MEMORY_STORE_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "memory_store")
)
DB_PATH = os.path.join(MEMORY_DIR, "projectpilot.db")
os.makedirs(MEMORY_DIR, exist_ok=True)

DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _run_migrations():
    """Run schema migrations for Phase 2 multi-workspace support."""
    conn = engine.connect()
    try:
        # Migration 1: Remove UNIQUE constraint from workspaces.owner_id
        # SQLite doesn't support ALTER TABLE DROP CONSTRAINT, so we check if unique index exists
        result = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='workspaces' AND name like '%owner%'")
        )
        idx = result.fetchone()
        if idx:
            # Drop the unique index on owner_id
            conn.execute(text("DROP INDEX IF EXISTS ix_workspaces_owner_id"))
            conn.execute(text("DROP INDEX IF EXISTS uq_workspaces_owner_id"))
            conn.commit()
            logger.info("Migration: removed UNIQUE constraint from workspaces.owner_id")
    except Exception as e:
        logger.warning("Migration note: %s", e)
    finally:
        conn.close()


def init_db():
    import database.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _run_migrations()
