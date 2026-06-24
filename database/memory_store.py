"""Persistent Memory Store — SQLite-backed cross-project learning and analytics.

Stores agent decisions, fix patterns, user preferences, and project analytics
for long-term memory across multiple generation sessions.
"""

import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MEMORY_DIR = os.getenv("MEMORY_STORE_DIR", "./memory_store")
MEMORY_DB = os.path.join(MEMORY_DIR, "projectpilot_memory.db")

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        Path(MEMORY_DIR).mkdir(parents=True, exist_ok=True)
        _local.conn = sqlite3.connect(MEMORY_DB, check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA synchronous=NORMAL")
    return _local.conn


def _migrate_workspace_id():
    """Add workspace_id and user_id columns to existing tables (safe to run multiple times)."""
    conn = _get_conn()
    migrations = [
        "ALTER TABLE agent_memory ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE project_analytics ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        # user_id isolation column — Phase 2 user-level history isolation
        "ALTER TABLE project_analytics ADD COLUMN user_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE project_insights ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE graph_sessions ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE autonomous_sessions ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE cost_tracking ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE chat_conversations ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE chat_conversations ADD COLUMN user_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE runtime_sessions ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE deployment_sessions ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE healing_sessions ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE learning_patterns ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE process_logs ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE benchmark_results ADD COLUMN workspace_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE agent_memory ADD COLUMN workspace_id_idx_added TEXT DEFAULT ''",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except Exception:
            pass
    conn.commit()


def init_db() -> None:
    conn = _get_conn()
    _migrate_workspace_id()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS agent_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            job_id TEXT NOT NULL,
            key TEXT,
            value TEXT,
            workspace_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_agent_memory_agent ON agent_memory(agent_name);
        CREATE INDEX IF NOT EXISTS idx_agent_memory_job ON agent_memory(job_id);

        CREATE TABLE IF NOT EXISTS fix_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT NOT NULL,
            pattern_signature TEXT NOT NULL,
            file_pattern TEXT,
            fix_description TEXT,
            success_count INTEGER DEFAULT 1,
            first_seen TEXT NOT NULL DEFAULT (datetime('now')),
            last_seen TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_fix_patterns_sig ON fix_patterns(pattern_signature);

        CREATE TABLE IF NOT EXISTS user_prefs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS project_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL UNIQUE,
            project_name TEXT DEFAULT '',
            agent_count INTEGER DEFAULT 0,
            file_count INTEGER DEFAULT 0,
            test_count INTEGER DEFAULT 0,
            test_passed INTEGER DEFAULT 0,
            token_usage INTEGER DEFAULT 0,
            total_duration_ms INTEGER DEFAULT 0,
            model_used TEXT DEFAULT '',
            status TEXT DEFAULT '',
            workspace_id TEXT NOT NULL DEFAULT '',
            user_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_analytics_user_id ON project_analytics(user_id);
        CREATE INDEX IF NOT EXISTS idx_analytics_ws_user ON project_analytics(workspace_id, user_id);

        CREATE TABLE IF NOT EXISTS coding_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pref_key TEXT NOT NULL,
            pref_value TEXT NOT NULL,
            source TEXT DEFAULT '',
            confidence REAL DEFAULT 1.0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_coding_prefs_key ON coding_preferences(pref_key);

        CREATE TABLE IF NOT EXISTS reusable_components (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            component_type TEXT NOT NULL,
            code TEXT NOT NULL,
            description TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            usage_count INTEGER DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_reusable_type ON reusable_components(component_type);

        CREATE TABLE IF NOT EXISTS project_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            insight_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            details TEXT DEFAULT '',
            workspace_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_insights_job ON project_insights(job_id);

        CREATE TABLE IF NOT EXISTS github_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            token TEXT NOT NULL,
            avatar_url TEXT DEFAULT '',
            name TEXT DEFAULT '',
            email TEXT DEFAULT '',
            public_repos INTEGER DEFAULT 0,
            connected_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS github_repos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            full_name TEXT NOT NULL,
            repo_data TEXT NOT NULL,
            synced_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(username, full_name)
        );

        CREATE TABLE IF NOT EXISTS chat_conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'New Chat',
            message_count INTEGER DEFAULT 0,
            workspace_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
            role TEXT NOT NULL CHECK(role IN ('user','assistant','system','tool')),
            content TEXT NOT NULL DEFAULT '',
            tool_calls TEXT,
            timestamp TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_chat_messages_conv ON chat_messages(conversation_id);

        -- v9 tables: Graph, Debate, Validation, Autonomous
        CREATE TABLE IF NOT EXISTS graph_sessions (
            id TEXT PRIMARY KEY,
            job_id TEXT DEFAULT '',
            graph_data TEXT NOT NULL DEFAULT '{}',
            status TEXT DEFAULT 'pending',
            workspace_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS debate_sessions (
            id TEXT PRIMARY KEY,
            topic TEXT NOT NULL,
            config TEXT DEFAULT '{}',
            results TEXT DEFAULT '[]',
            final_solution TEXT DEFAULT '',
            consensus_score REAL DEFAULT 0.0,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS validation_journeys (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            base_url TEXT NOT NULL,
            steps TEXT DEFAULT '[]',
            tags TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS autonomous_sessions (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            config TEXT DEFAULT '{}',
            iterations TEXT DEFAULT '[]',
            status TEXT DEFAULT 'pending',
            total_tokens INTEGER DEFAULT 0,
            total_cost REAL DEFAULT 0.0,
            initial_score REAL DEFAULT 0.0,
            final_score REAL DEFAULT 0.0,
            improvement_pct REAL DEFAULT 0.0,
            workspace_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS cost_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            session_type TEXT NOT NULL,
            provider TEXT DEFAULT '',
            tokens_used INTEGER DEFAULT 0,
            cost REAL DEFAULT 0.0,
            duration_ms INTEGER DEFAULT 0,
            workspace_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_cost_job ON cost_tracking(job_id);

        -- v10 tables: Runtime, Deployment, Healing, Learning, Process Logs, Checkpoints
        CREATE TABLE IF NOT EXISTS runtime_sessions (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            name TEXT DEFAULT '',
            status TEXT DEFAULT 'created',
            runtime_type TEXT DEFAULT 'subprocess',
            container_id TEXT,
            pid INTEGER,
            port INTEGER,
            host TEXT DEFAULT 'localhost',
            environment TEXT DEFAULT '{}',
            error TEXT,
            started_at REAL,
            stopped_at REAL,
            metadata TEXT DEFAULT '{}',
            workspace_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS runtime_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            runtime_id TEXT NOT NULL,
            cpu_percent REAL DEFAULT 0.0,
            memory_mb REAL DEFAULT 0.0,
            disk_mb REAL DEFAULT 0.0,
            network_rx INTEGER DEFAULT 0,
            network_tx INTEGER DEFAULT 0,
            response_time_ms REAL DEFAULT 0.0,
            error_count INTEGER DEFAULT 0,
            restart_count INTEGER DEFAULT 0,
            uptime REAL DEFAULT 0.0,
            timestamp REAL DEFAULT (strftime('%s','now'))
        );
        CREATE INDEX IF NOT EXISTS idx_runtime_metrics_id ON runtime_metrics(runtime_id);

        CREATE TABLE IF NOT EXISTS deployment_sessions (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            project_dir TEXT NOT NULL,
            target TEXT DEFAULT 'docker',
            status TEXT DEFAULT 'pending',
            url TEXT,
            build_log TEXT DEFAULT '',
            deploy_log TEXT DEFAULT '',
            health_check_ok INTEGER,
            error TEXT,
            workspace_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS healing_sessions (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            runtime_id TEXT DEFAULT '',
            status TEXT DEFAULT 'detected',
            error_type TEXT DEFAULT '',
            root_cause TEXT DEFAULT '',
            fix_description TEXT DEFAULT '',
            fix_applied INTEGER DEFAULT 0,
            tests_passed INTEGER,
            attempt INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            patches TEXT DEFAULT '[]',
            metadata TEXT DEFAULT '{}',
            workspace_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS learning_patterns (
            id TEXT PRIMARY KEY,
            pattern_type TEXT NOT NULL,
            pattern_key TEXT NOT NULL,
            value TEXT DEFAULT '',
            success_count INTEGER DEFAULT 1,
            confidence REAL DEFAULT 1.0,
            tags TEXT DEFAULT '[]',
            job_id TEXT DEFAULT '',
            workspace_id TEXT NOT NULL DEFAULT '',
            created_at REAL,
            last_used REAL
        );
        CREATE INDEX IF NOT EXISTS idx_learning_type ON learning_patterns(pattern_type);

        CREATE TABLE IF NOT EXISTS process_logs (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            runtime_type TEXT DEFAULT '',
            command TEXT DEFAULT '',
            status TEXT DEFAULT '',
            stdout TEXT DEFAULT '',
            stderr TEXT DEFAULT '',
            exit_code INTEGER,
            duration_ms REAL DEFAULT 0.0,
            error TEXT,
            workspace_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS runtime_checkpoints (
            id TEXT PRIMARY KEY,
            runtime_id TEXT NOT NULL,
            checkpoint_data TEXT DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_checkpoint_runtime ON runtime_checkpoints(runtime_id);

        -- v10.1 tables: Benchmark Results
        CREATE TABLE IF NOT EXISTS benchmark_results (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            autonomy_score REAL DEFAULT 0.0,
            metrics TEXT DEFAULT '{}',
            features_passed TEXT DEFAULT '[]',
            features_failed TEXT DEFAULT '[]',
            feature_total INTEGER DEFAULT 0,
            error TEXT,
            model TEXT DEFAULT 'local',
            iteration INTEGER DEFAULT 1,
            logs TEXT DEFAULT '[]',
            created_at REAL,
            completed_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_benchmark_domain ON benchmark_results(domain);
        CREATE INDEX IF NOT EXISTS idx_benchmark_score ON benchmark_results(autonomy_score DESC);

        -- v11 tables: Organization, Repositories, Relationships, Cross-repo Changes, Impact Reports
        CREATE TABLE IF NOT EXISTS organizations (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL DEFAULT '',
            description TEXT DEFAULT '',
            repo_count INTEGER DEFAULT 0,
            entity_count INTEGER DEFAULT 0,
            metadata TEXT DEFAULT '{}',
            created_at REAL,
            updated_at REAL
        );

        CREATE TABLE IF NOT EXISTS repositories (
            id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            path TEXT DEFAULT '',
            category TEXT DEFAULT 'other',
            language TEXT DEFAULT '',
            url TEXT DEFAULT '',
            description TEXT DEFAULT '',
            file_count INTEGER DEFAULT 0,
            indexed_at REAL,
            metadata TEXT DEFAULT '{}',
            FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_repositories_org ON repositories(org_id);

        CREATE TABLE IF NOT EXISTS repository_relationships (
            id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            source_repo TEXT NOT NULL,
            target_repo TEXT NOT NULL,
            source_file TEXT DEFAULT '',
            target_file TEXT DEFAULT '',
            relationship TEXT DEFAULT 'depends_on',
            weight REAL DEFAULT 1.0,
            verified INTEGER DEFAULT 0,
            FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_repo_rels_org ON repository_relationships(org_id);

        CREATE TABLE IF NOT EXISTS cross_repo_changes (
            id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            branch_name TEXT DEFAULT '',
            description TEXT DEFAULT '',
            repos_affected TEXT DEFAULT '[]',
            files_changed TEXT DEFAULT '[]',
            status TEXT DEFAULT 'pending',
            pr_urls TEXT DEFAULT '[]',
            created_at REAL,
            completed_at REAL,
            FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_cross_repo_changes_org ON cross_repo_changes(org_id);

        CREATE TABLE IF NOT EXISTS impact_reports (
            id TEXT PRIMARY KEY,
            org_id TEXT NOT NULL,
            query TEXT DEFAULT '',
            affected_repos TEXT DEFAULT '[]',
            affected_files TEXT DEFAULT '[]',
            impact_score REAL DEFAULT 0.0,
            risk_level TEXT DEFAULT 'low',
            recommendations TEXT DEFAULT '[]',
            report_markdown TEXT DEFAULT '',
            created_at REAL,
            FOREIGN KEY (org_id) REFERENCES organizations(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_impact_reports_org ON impact_reports(org_id);

        -- v11.1 Plugin & Agent SDK tables
        CREATE TABLE IF NOT EXISTS plugins (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version TEXT DEFAULT '1.0.0',
            author TEXT DEFAULT '',
            description TEXT DEFAULT '',
            plugin_type TEXT DEFAULT 'tool',
            source TEXT DEFAULT '',
            enabled INTEGER DEFAULT 0,
            manifest_json TEXT DEFAULT '{}',
            permissions_json TEXT DEFAULT '[]',
            resource_limits_json TEXT DEFAULT '{}',
            checksum TEXT DEFAULT '',
            installed_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_plugins_name ON plugins(name);
        CREATE INDEX IF NOT EXISTS idx_plugins_type ON plugins(plugin_type);

        CREATE TABLE IF NOT EXISTS marketplace_packages (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version TEXT DEFAULT '1.0.0',
            author TEXT DEFAULT '',
            description TEXT DEFAULT '',
            package_type TEXT DEFAULT 'plugin',
            manifest_json TEXT DEFAULT '{}',
            downloads INTEGER DEFAULT 0,
            rating REAL DEFAULT 0.0,
            rating_count INTEGER DEFAULT 0,
            tags_json TEXT DEFAULT '[]',
            published_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            readme TEXT DEFAULT '',
            compatibility TEXT DEFAULT '>=11.0.0',
            verified INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_marketplace_name ON marketplace_packages(name);
        CREATE INDEX IF NOT EXISTS idx_marketplace_type ON marketplace_packages(package_type);

        CREATE TABLE IF NOT EXISTS custom_agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version TEXT DEFAULT '1.0.0',
            description TEXT DEFAULT '',
            source TEXT DEFAULT '',
            capabilities_json TEXT DEFAULT '[]',
            hooks_json TEXT DEFAULT '{}',
            config_json TEXT DEFAULT '{}',
            enabled INTEGER DEFAULT 0,
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_custom_agents_name ON custom_agents(name);

        CREATE TABLE IF NOT EXISTS custom_workflows (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            version TEXT DEFAULT '1.0.0',
            description TEXT DEFAULT '',
            source TEXT DEFAULT '',
            steps_json TEXT DEFAULT '[]',
            status TEXT DEFAULT 'pending',
            config_json TEXT DEFAULT '{}',
            enabled INTEGER DEFAULT 0,
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_custom_workflows_name ON custom_workflows(name);

        -- v12.0 Continuous Autonomous Evaluation tables
        CREATE TABLE IF NOT EXISTS evaluation_runs (
            id TEXT PRIMARY KEY,
            trigger_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            autonomy_score REAL DEFAULT 0.0,
            success_rate REAL DEFAULT 0.0,
            total_cost REAL DEFAULT 0.0,
            total_runtime REAL DEFAULT 0.0,
            healing_rate REAL DEFAULT 0.0,
            deployment_success_rate REAL DEFAULT 0.0,
            benchmark_score REAL DEFAULT 0.0,
            tasks_completed INTEGER DEFAULT 0,
            tasks_failed INTEGER DEFAULT 0,
            error_log TEXT DEFAULT '',
            started_at REAL,
            completed_at REAL,
            created_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_evaluation_runs_trigger ON evaluation_runs(trigger_type);
        CREATE INDEX IF NOT EXISTS idx_evaluation_runs_status ON evaluation_runs(status);

        CREATE TABLE IF NOT EXISTS evaluation_reports (
            id TEXT PRIMARY KEY,
            report_type TEXT NOT NULL,
            title TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            metrics_json TEXT DEFAULT '{}',
            trends_json TEXT DEFAULT '{}',
            regressions_found TEXT DEFAULT '[]',
            improvements_found TEXT DEFAULT '[]',
            recommendations TEXT DEFAULT '[]',
            report_markdown TEXT DEFAULT '',
            period_start REAL,
            period_end REAL,
            created_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_eval_reports_type ON evaluation_reports(report_type);
        CREATE INDEX IF NOT EXISTS idx_eval_reports_created ON evaluation_reports(created_at);

        CREATE TABLE IF NOT EXISTS regressions (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            severity TEXT DEFAULT 'low',
            metric TEXT DEFAULT '',
            previous_value REAL DEFAULT 0.0,
            current_value REAL DEFAULT 0.0,
            change_pct REAL DEFAULT 0.0,
            title TEXT DEFAULT '',
            description TEXT DEFAULT '',
            dismissed INTEGER DEFAULT 0,
            run_id TEXT DEFAULT '',
            created_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_regressions_category ON regressions(category);
        CREATE INDEX IF NOT EXISTS idx_regressions_severity ON regressions(severity);

        CREATE TABLE IF NOT EXISTS leaderboards (
            id TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            entry_name TEXT NOT NULL,
            score REAL DEFAULT 0.0,
            autonomy_score REAL DEFAULT 0.0,
            reliability_score REAL DEFAULT 0.0,
            cost_efficiency REAL DEFAULT 0.0,
            run_count INTEGER DEFAULT 0,
            metadata_json TEXT DEFAULT '{}',
            last_updated REAL
        );
        CREATE INDEX IF NOT EXISTS idx_leaderboards_category ON leaderboards(category);
        CREATE INDEX IF NOT EXISTS idx_leaderboards_score ON leaderboards(score DESC);

        CREATE TABLE IF NOT EXISTS version_history (
            id TEXT PRIMARY KEY,
            version TEXT NOT NULL,
            snapshot_data TEXT DEFAULT '{}',
            snapshot_type TEXT DEFAULT 'full',
            created_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_version_history_version ON version_history(version);

        CREATE TABLE IF NOT EXISTS version_comparisons (
            id TEXT PRIMARY KEY,
            from_version TEXT NOT NULL,
            to_version TEXT NOT NULL,
            deltas TEXT DEFAULT '{}',
            summary TEXT DEFAULT '',
            created_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_version_comparisons_versions ON version_comparisons(from_version, to_version);

        -- v12 Phase 4 — Scheduler metadata (persistent config + recovery)
        CREATE TABLE IF NOT EXISTS scheduler_metadata (
            id TEXT PRIMARY KEY,
            schedule_type TEXT NOT NULL UNIQUE,
            enabled INTEGER DEFAULT 1,
            interval_hours REAL DEFAULT 24.0,
            window_start_utc TEXT DEFAULT '02:00',
            day_of_week INTEGER DEFAULT 0,
            execution_time_utc TEXT DEFAULT '02:00',
            domain_timeout_seconds REAL DEFAULT 300.0,
            parallel_execution INTEGER DEFAULT 0,
            last_run_at REAL,
            next_run_at REAL,
            recovery_window_hours REAL DEFAULT 6.0,
            created_at REAL,
            updated_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_scheduler_metadata_type ON scheduler_metadata(schedule_type);

        -- v12.5 — Learning Engine Feedback Loop
        CREATE TABLE IF NOT EXISTS learning_feedback (
            id TEXT PRIMARY KEY,
            feedback_type TEXT NOT NULL,
            source TEXT DEFAULT '',
            category TEXT DEFAULT '',
            score REAL DEFAULT 0.0,
            metric_name TEXT DEFAULT '',
            metric_value REAL DEFAULT 0.0,
            context_json TEXT DEFAULT '{}',
            run_id TEXT DEFAULT '',
            version TEXT DEFAULT '',
            created_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_learn_feedback_type ON learning_feedback(feedback_type);
        CREATE INDEX IF NOT EXISTS idx_learn_feedback_category ON learning_feedback(category);
        CREATE INDEX IF NOT EXISTS idx_learn_feedback_run ON learning_feedback(run_id);

        CREATE TABLE IF NOT EXISTS learning_feedback_patterns (
            id TEXT PRIMARY KEY,
            pattern_type TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT DEFAULT '',
            description TEXT DEFAULT '',
            strategy TEXT DEFAULT '',
            outcome TEXT DEFAULT '',
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.0,
            tags TEXT DEFAULT '[]',
            source_run_ids TEXT DEFAULT '[]',
            created_at REAL,
            updated_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_learn_fb_patterns_type ON learning_feedback_patterns(pattern_type);
        CREATE INDEX IF NOT EXISTS idx_learn_fb_patterns_cat ON learning_feedback_patterns(category);
        CREATE INDEX IF NOT EXISTS idx_learn_fb_patterns_conf ON learning_feedback_patterns(confidence DESC);

        CREATE TABLE IF NOT EXISTS learning_feedback_recommendations (
            id TEXT PRIMARY KEY,
            recommendation_type TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT DEFAULT '',
            description TEXT DEFAULT '',
            priority TEXT DEFAULT 'medium',
            rationale TEXT DEFAULT '',
            expected_impact TEXT DEFAULT '',
            implementation_suggestions TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            source_pattern_ids TEXT DEFAULT '[]',
            created_at REAL,
            updated_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_learn_fb_recs_type ON learning_feedback_recommendations(recommendation_type);
        CREATE INDEX IF NOT EXISTS idx_learn_fb_recs_cat ON learning_feedback_recommendations(category);
        CREATE INDEX IF NOT EXISTS idx_learn_fb_recs_priority ON learning_feedback_recommendations(priority);

        CREATE TABLE IF NOT EXISTS campaigns (
            id TEXT PRIMARY KEY,
            name TEXT DEFAULT '',
            status TEXT DEFAULT 'pending',
            config TEXT DEFAULT '{}',
            total_runs INTEGER DEFAULT 0,
            completed_runs INTEGER DEFAULT 0,
            failed_runs INTEGER DEFAULT 0,
            domains TEXT DEFAULT '[]',
            created_at REAL,
            started_at REAL,
            completed_at REAL,
            error TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);

        CREATE TABLE IF NOT EXISTS campaign_runs (
            id TEXT PRIMARY KEY,
            campaign_id TEXT NOT NULL,
            domain TEXT NOT NULL,
            iteration INTEGER DEFAULT 1,
            status TEXT DEFAULT 'pending',
            autonomy_score REAL DEFAULT 0.0,
            execution_time REAL DEFAULT 0.0,
            cost REAL DEFAULT 0.0,
            tests_generated INTEGER DEFAULT 0,
            tests_passed INTEGER DEFAULT 0,
            healing_iterations INTEGER DEFAULT 0,
            deployment_success INTEGER DEFAULT 0,
            benchmark_success INTEGER DEFAULT 0,
            error TEXT DEFAULT '',
            created_at REAL,
            completed_at REAL
        );
        CREATE INDEX IF NOT EXISTS idx_campaign_runs_campaign ON campaign_runs(campaign_id);
        CREATE INDEX IF NOT EXISTS idx_campaign_runs_status ON campaign_runs(status);
    """)
    conn.commit()
    # Initialize audit table
    from services.audit_service import init_audit_db

    init_audit_db()
    logger.info("Memory store ready at %s", MEMORY_DB)


def store_agent_memory(agent_name: str, job_id: str, key: str, value: str, workspace_id: str = "") -> None:
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO agent_memory (agent_name, job_id, key, value, workspace_id) VALUES (?, ?, ?, ?, ?)",
            (agent_name, job_id, key, value, workspace_id),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("Memory store failed: %s", exc)


def get_agent_memory(agent_name: str, key: str | None = None, workspace_id: str = "", limit: int = 50) -> list[dict]:
    try:
        conn = _get_conn()
        if key:
            cur = conn.execute(
                "SELECT * FROM agent_memory WHERE agent_name=? AND key=? AND workspace_id=? ORDER BY id DESC LIMIT ?",
                (agent_name, key, workspace_id, limit),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM agent_memory WHERE agent_name=? AND workspace_id=? ORDER BY id DESC LIMIT ?",
                (agent_name, workspace_id, limit),
            )
        return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("Memory read failed: %s", exc)
        return []


def record_fix_pattern(error_type: str, error_text: str, file_pattern: str, fix_desc: str) -> None:
    try:
        import hashlib

        sig = hashlib.md5(error_text[:200].encode()).hexdigest()
        conn = _get_conn()
        existing = conn.execute(
            "SELECT id, success_count FROM fix_patterns WHERE pattern_signature=?",
            (sig,),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE fix_patterns SET success_count=success_count+1, last_seen=datetime('now') WHERE id=?",
                (existing["id"],),
            )
        else:
            conn.execute(
                "INSERT INTO fix_patterns (pattern_type, pattern_signature, file_pattern, fix_description) "
                "VALUES (?, ?, ?, ?)",
                (error_type, sig, file_pattern, fix_desc[:500]),
            )
        conn.commit()
    except Exception as exc:
        logger.warning("Fix pattern record failed: %s", exc)


def get_fix_patterns(error_type: str | None = None, limit: int = 20) -> list[dict]:
    try:
        conn = _get_conn()
        if error_type:
            cur = conn.execute(
                "SELECT * FROM fix_patterns WHERE pattern_type=? ORDER BY success_count DESC LIMIT ?",
                (error_type, limit),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM fix_patterns ORDER BY success_count DESC LIMIT ?",
                (limit,),
            )
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def set_preference(key: str, value: str) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO user_prefs (key, value, updated_at) VALUES (?, ?, datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=datetime('now')",
            (key, value),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("Preference save failed: %s", exc)


def get_preference(key: str, default: str = "") -> str:
    try:
        conn = _get_conn()
        r = conn.execute("SELECT value FROM user_prefs WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default
    except Exception:
        return default


def record_project_analytics(
    job_id: str,
    project_name: str = "",
    agent_count: int = 0,
    file_count: int = 0,
    test_count: int = 0,
    test_passed: int = 0,
    token_usage: int = 0,
    total_duration_ms: int = 0,
    model_used: str = "",
    status: str = "",
    workspace_id: str = "",
    user_id: str = "",
) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO project_analytics
               (job_id, project_name, agent_count, file_count, test_count, test_passed,
                token_usage, total_duration_ms, model_used, status, workspace_id, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                project_name=excluded.project_name, agent_count=excluded.agent_count,
                file_count=excluded.file_count,
                test_count=excluded.test_count, test_passed=excluded.test_passed,
                token_usage=excluded.token_usage, total_duration_ms=excluded.total_duration_ms,
                model_used=excluded.model_used, status=excluded.status,
                workspace_id=excluded.workspace_id, user_id=excluded.user_id""",
            (
                job_id,
                project_name,
                agent_count,
                file_count,
                test_count,
                test_passed,
                token_usage,
                total_duration_ms,
                model_used,
                status,
                workspace_id,
                user_id,
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("Analytics record failed: %s", exc)


def get_project_analytics(workspace_id: str = "", user_id: str = "", limit: int = 50) -> list[dict]:
    try:
        conn = _get_conn()
        if workspace_id and user_id:
            cur = conn.execute(
                "SELECT * FROM project_analytics WHERE workspace_id=? AND user_id=? ORDER BY created_at DESC LIMIT ?",
                (workspace_id, user_id, limit),
            )
        elif workspace_id:
            cur = conn.execute(
                "SELECT * FROM project_analytics WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?",
                (workspace_id, limit),
            )
        elif user_id:
            cur = conn.execute(
                "SELECT * FROM project_analytics WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM project_analytics ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def delete_project_analytics(job_id: str, workspace_id: str = "", user_id: str = "") -> bool:
    try:
        conn = _get_conn()
        if workspace_id and user_id:
            conn.execute(
                "DELETE FROM project_analytics WHERE job_id = ? AND workspace_id = ? AND user_id = ?",
                (job_id, workspace_id, user_id),
            )
        elif workspace_id:
            conn.execute("DELETE FROM project_analytics WHERE job_id = ? AND workspace_id = ?", (job_id, workspace_id))
        else:
            conn.execute("DELETE FROM project_analytics WHERE job_id = ?", (job_id,))
        conn.commit()
        logger.info("Deleted analytics for job %s (ws=%s, uid=%s)", job_id, workspace_id, user_id)
        return True
    except Exception as exc:
        logger.warning("Failed to delete analytics for %s: %s", job_id, exc)
        return False


def get_analytics_summary(workspace_id: str = "") -> dict[str, Any]:
    try:
        conn = _get_conn()
        ws_clause = " WHERE workspace_id=? " if workspace_id else " "
        ws_param = (workspace_id,) if workspace_id else ()
        projects = conn.execute(f"SELECT COUNT(*) as c FROM project_analytics{ws_clause}", ws_param).fetchone()
        total_tokens = conn.execute(
            f"SELECT COALESCE(SUM(token_usage),0) as t FROM project_analytics{ws_clause}", ws_param
        ).fetchone()
        total_files = conn.execute(
            f"SELECT COALESCE(SUM(file_count),0) as f FROM project_analytics{ws_clause}", ws_param
        ).fetchone()
        total_tests = conn.execute(
            f"SELECT COALESCE(SUM(test_count),0) as t FROM project_analytics{ws_clause}", ws_param
        ).fetchone()
        avg_duration_ws = f" AND workspace_id=? " if workspace_id else " "
        avg_duration = conn.execute(
            f"SELECT COALESCE(AVG(total_duration_ms),0) as a FROM project_analytics WHERE total_duration_ms>0{avg_duration_ws}",
            (workspace_id,) if workspace_id else (),
        ).fetchone()
        return {
            "total_projects": projects["c"] if projects else 0,
            "total_tokens": total_tokens["t"] if total_tokens else 0,
            "total_files": total_files["f"] if total_files else 0,
            "total_tests": total_tests["t"] if total_tests else 0,
            "avg_duration_ms": round(avg_duration["a"], 0) if avg_duration else 0,
        }
    except Exception:
        return {}


# ── Coding Preferences ───────────────────────────────────────────────────


def set_coding_preference(pref_key: str, pref_value: str, source: str = "", confidence: float = 1.0) -> None:
    try:
        conn = _get_conn()
        existing = conn.execute("SELECT id FROM coding_preferences WHERE pref_key=?", (pref_key,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE coding_preferences SET pref_value=?, source=?, confidence=?, updated_at=datetime('now') WHERE id=?",
                (pref_value, source, confidence, existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO coding_preferences (pref_key, pref_value, source, confidence) VALUES (?, ?, ?, ?)",
                (pref_key, pref_value, source, confidence),
            )
        conn.commit()
    except Exception as exc:
        logger.warning("set_coding_preference failed: %s", exc)


def get_coding_preferences(limit: int = 50) -> list[dict]:
    try:
        conn = _get_conn()
        cur = conn.execute(
            "SELECT * FROM coding_preferences ORDER BY confidence DESC, updated_at DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


# ── Reusable Components ───────────────────────────────────────────────────


def save_reusable_component(name: str, component_type: str, code: str, description: str = "", tags: str = "") -> None:
    try:
        conn = _get_conn()
        existing = conn.execute(
            "SELECT id, usage_count FROM reusable_components WHERE name=? AND component_type=?", (name, component_type)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE reusable_components SET usage_count=usage_count+1, updated_at=datetime('now') WHERE id=?",
                (existing["id"],),
            )
        else:
            conn.execute(
                "INSERT INTO reusable_components (name, component_type, code, description, tags) VALUES (?, ?, ?, ?, ?)",
                (name, component_type, code, description, tags),
            )
        conn.commit()
    except Exception as exc:
        logger.warning("save_reusable_component failed: %s", exc)


def get_reusable_components(component_type: str | None = None, limit: int = 20) -> list[dict]:
    try:
        conn = _get_conn()
        if component_type:
            cur = conn.execute(
                "SELECT * FROM reusable_components WHERE component_type=? ORDER BY usage_count DESC LIMIT ?",
                (component_type, limit),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM reusable_components ORDER BY usage_count DESC LIMIT ?",
                (limit,),
            )
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


# ── Project Insights ─────────────────────────────────────────────────────


def save_project_insight(
    job_id: str, insight_type: str, summary: str, details: str = "", workspace_id: str = ""
) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO project_insights (job_id, insight_type, summary, details, workspace_id) VALUES (?, ?, ?, ?, ?)",
            (job_id, insight_type, summary, details, workspace_id),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("save_project_insight failed: %s", exc)


def get_project_insights(insight_type: str | None = None, workspace_id: str = "", limit: int = 50) -> list[dict]:
    try:
        conn = _get_conn()
        if insight_type:
            cur = conn.execute(
                "SELECT * FROM project_insights WHERE insight_type=? AND workspace_id=? ORDER BY created_at DESC LIMIT ?",
                (insight_type, workspace_id, limit),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM project_insights WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?",
                (workspace_id, limit),
            )
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


# ── GitHub Connection CRUD ───────────────────────────────────────────────


def save_github_connection(username: str, data: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO github_connections (username, token, avatar_url, name, email, public_repos, connected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(username) DO UPDATE SET
               token=excluded.token, avatar_url=excluded.avatar_url, name=excluded.name,
               email=excluded.email, public_repos=excluded.public_repos,
               connected_at=excluded.connected_at""",
            (
                data["username"],
                data["token"],
                data.get("avatar_url", ""),
                data.get("name", ""),
                data.get("email", ""),
                data.get("public_repos", 0),
                data.get("connected_at", ""),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("save_github_connection failed: %s", exc)


def get_github_connection(username: str = "") -> Any:
    try:
        conn = _get_conn()
        if username:
            cur = conn.execute("SELECT * FROM github_connections WHERE username=?", (username,))
            row = cur.fetchone()
            return dict(row) if row else None
        cur = conn.execute("SELECT * FROM github_connections ORDER BY connected_at DESC")
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return [] if not username else None


def delete_github_connection(username: str) -> None:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM github_connections WHERE username=?", (username,))
        conn.commit()
    except Exception as exc:
        logger.warning("delete_github_connection failed: %s", exc)


# ── GitHub Repo CRUD ─────────────────────────────────────────────────────


def save_github_repo(username: str, full_name: str, repo_data: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO github_repos (username, full_name, repo_data, synced_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(username, full_name) DO UPDATE SET
               repo_data=excluded.repo_data, synced_at=excluded.synced_at""",
            (username, full_name, json.dumps(repo_data)),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("save_github_repo failed: %s", exc)


def get_github_repos(username: str = "") -> list[dict]:
    try:
        conn = _get_conn()
        if username:
            cur = conn.execute("SELECT * FROM github_repos WHERE username=? ORDER BY synced_at DESC", (username,))
        else:
            cur = conn.execute("SELECT * FROM github_repos ORDER BY synced_at DESC")
        results = []
        for r in cur.fetchall():
            d = dict(r)
            try:
                d["repo_data"] = json.loads(d["repo_data"])
            except Exception:
                d["repo_data"] = {}
            results.append(d)
        return results
    except Exception:
        return []


def delete_github_repo(full_name: str) -> None:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM github_repos WHERE full_name=?", (full_name,))
        conn.commit()
    except Exception as exc:
        logger.warning("delete_github_repo failed: %s", exc)


# ── Chat Conversations CRUD ───────────────────────────────────────────────


def create_chat_conversation(
    title: str = "New Chat", conversation_id: str | None = None, workspace_id: str = "", user_id: str = ""
) -> str:
    try:
        conn = _get_conn()
        cid = conversation_id or str(uuid.uuid4())
        conn.execute(
            "INSERT INTO chat_conversations (id, title, workspace_id, user_id) VALUES (?, ?, ?, ?)",
            (cid, title, workspace_id, user_id),
        )
        conn.commit()
        return cid
    except Exception as exc:
        logger.warning("create_chat_conversation failed: %s", exc)
        return ""


def add_chat_message(conversation_id: str, role: str, content: str, tool_calls: str | None = None) -> None:
    try:
        conn = _get_conn()
        mid = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO chat_messages (id, conversation_id, role, content, tool_calls) VALUES (?, ?, ?, ?, ?)",
            (mid, conversation_id, role, content, tool_calls),
        )
        conn.execute(
            "UPDATE chat_conversations SET message_count=message_count+1, updated_at=datetime('now') WHERE id=?",
            (conversation_id,),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("add_chat_message failed: %s", exc)


def get_chat_messages(conversation_id: str, limit: int = 50) -> list[dict]:
    try:
        conn = _get_conn()
        cur = conn.execute(
            "SELECT * FROM chat_messages WHERE conversation_id=? ORDER BY timestamp ASC LIMIT ?",
            (conversation_id, limit),
        )
        return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("get_chat_messages failed: %s", exc)
        return []


def get_chat_conversation(conversation_id: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute(
            "SELECT * FROM chat_conversations WHERE id=?",
            (conversation_id,),
        )
        r = cur.fetchone()
        return dict(r) if r else None
    except Exception as exc:
        logger.warning("get_chat_conversation failed: %s", exc)
        return None


def verify_conversation_ownership(conversation_id: str, user_id: str) -> bool:
    conv = get_chat_conversation(conversation_id)
    if not conv:
        return False
    return conv.get("user_id") == user_id


def list_chat_conversations(workspace_id: str = "", user_id: str = "", limit: int = 20) -> list[dict]:
    try:
        conn = _get_conn()
        if workspace_id and user_id:
            cur = conn.execute(
                "SELECT * FROM chat_conversations WHERE workspace_id=? AND user_id=? ORDER BY updated_at DESC LIMIT ?",
                (workspace_id, user_id, limit),
            )
        elif workspace_id:
            cur = conn.execute(
                "SELECT * FROM chat_conversations WHERE workspace_id=? ORDER BY updated_at DESC LIMIT ?",
                (workspace_id, limit),
            )
        else:
            return []
        return [dict(r) for r in cur.fetchall()]
    except Exception as exc:
        logger.warning("list_chat_conversations failed: %s", exc)
        return []


def update_chat_conversation_title(conversation_id: str, title: str) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            "UPDATE chat_conversations SET title=?, updated_at=datetime('now') WHERE id=?",
            (title, conversation_id),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("update_chat_conversation_title failed: %s", exc)


def delete_chat_conversation(conversation_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM chat_messages WHERE conversation_id=?", (conversation_id,))
        conn.execute("DELETE FROM chat_conversations WHERE id=?", (conversation_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_chat_conversation failed: %s", exc)
        return False


# ── v9: Cost Tracking ─────────────────────────────────────────────────────


def record_cost(
    job_id: str,
    session_type: str,
    tokens_used: int,
    cost: float,
    duration_ms: int = 0,
    provider: str = "",
    workspace_id: str = "",
) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO cost_tracking (job_id, session_type, provider, tokens_used, cost, duration_ms, workspace_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (job_id, session_type, provider, tokens_used, cost, duration_ms, workspace_id),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("record_cost failed: %s", exc)


def get_cost_summary(job_id: str | None = None, workspace_id: str = "") -> dict[str, Any]:
    try:
        conn = _get_conn()
        if job_id:
            cur = conn.execute(
                "SELECT COUNT(*) as sessions, COALESCE(SUM(tokens_used),0) as tokens, "
                "COALESCE(SUM(cost),0) as cost FROM cost_tracking WHERE job_id=?",
                (job_id,),
            )
        elif workspace_id:
            cur = conn.execute(
                "SELECT COUNT(*) as sessions, COALESCE(SUM(tokens_used),0) as tokens, "
                "COALESCE(SUM(cost),0) as cost FROM cost_tracking WHERE workspace_id=?",
                (workspace_id,),
            )
        else:
            cur = conn.execute(
                "SELECT COUNT(*) as sessions, COALESCE(SUM(tokens_used),0) as tokens, "
                "COALESCE(SUM(cost),0) as cost FROM cost_tracking"
            )
        row = cur.fetchone()
        return dict(row) if row else {"sessions": 0, "tokens": 0, "cost": 0}
    except Exception:
        return {}


def save_iteration_history(job_id: str, session_id: str, iteration_data: str, workspace_id: str = "") -> None:
    try:
        conn = _get_conn()
        existing = conn.execute("SELECT id, iterations FROM autonomous_sessions WHERE id=?", (session_id,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE autonomous_sessions SET iterations=? WHERE id=?",
                (iteration_data, session_id),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO autonomous_sessions (id, job_id, iterations, workspace_id) VALUES (?, ?, ?, ?)",
                (session_id, job_id, iteration_data, workspace_id),
            )
        conn.commit()
    except Exception as exc:
        logger.warning("save_iteration_history failed: %s", exc)


def get_iteration_history(job_id: str, workspace_id: str = "", limit: int = 10) -> list[dict]:
    try:
        conn = _get_conn()
        cur = conn.execute(
            "SELECT * FROM autonomous_sessions WHERE job_id=? ORDER BY created_at DESC LIMIT ?",
            (job_id, limit),
        )
        results = []
        for r in cur.fetchall():
            d = dict(r)
            try:
                d["iterations"] = json.loads(d["iterations"]) if isinstance(d["iterations"], str) else d["iterations"]
            except Exception:
                pass
            results.append(d)
        return results
    except Exception:
        return []


def save_graph_session(
    graph_id: str, job_id: str, graph_data: str, status: str = "pending", workspace_id: str = ""
) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO graph_sessions (id, job_id, graph_data, status, workspace_id) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET graph_data=excluded.graph_data, status=excluded.status, workspace_id=excluded.workspace_id, updated_at=datetime('now')",
            (graph_id, job_id, graph_data, status, workspace_id),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("save_graph_session failed: %s", exc)


def get_graph_session(graph_id: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM graph_sessions WHERE id=?", (graph_id,))
        r = cur.fetchone()
        return dict(r) if r else None
    except Exception:
        return None


def list_graph_sessions(workspace_id: str = "", limit: int = 20) -> list[dict]:
    try:
        conn = _get_conn()
        if workspace_id:
            cur = conn.execute(
                "SELECT * FROM graph_sessions WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?",
                (workspace_id, limit),
            )
        else:
            cur = conn.execute("SELECT * FROM graph_sessions ORDER BY created_at DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


# ── Benchmark Results ──────────────────────────────────────────────────────────


def save_benchmark_result(result_data: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO benchmark_results (id, run_id, domain, status, autonomy_score, metrics,
               features_passed, features_failed, feature_total, error, model, iteration, logs, created_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
               status=excluded.status, autonomy_score=excluded.autonomy_score,
               metrics=excluded.metrics, completed_at=excluded.completed_at""",
            (
                result_data["id"],
                result_data.get("run_id", ""),
                result_data.get("domain", ""),
                result_data.get("status", "pending"),
                result_data.get("autonomy_score", 0.0),
                json.dumps(result_data.get("metrics", {})),
                json.dumps(result_data.get("features_passed", [])),
                json.dumps(result_data.get("features_failed", [])),
                result_data.get("feature_total", 0),
                result_data.get("error"),
                result_data.get("model", "local"),
                result_data.get("iteration", 1),
                json.dumps(result_data.get("logs", [])),
                result_data.get("created_at"),
                result_data.get("completed_at"),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("save_benchmark_result failed: %s", exc)


def get_benchmark_results(domain: str | None = None, limit: int = 50) -> list[dict]:
    try:
        conn = _get_conn()
        if domain:
            cur = conn.execute(
                "SELECT * FROM benchmark_results WHERE domain=? ORDER BY created_at DESC LIMIT ?",
                (domain, limit),
            )
        else:
            cur = conn.execute(
                "SELECT * FROM benchmark_results ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["metrics"] = json.loads(d.get("metrics", "{}"))
            d["features_passed"] = json.loads(d.get("features_passed", "[]"))
            d["features_failed"] = json.loads(d.get("features_failed", "[]"))
            d["logs"] = json.loads(d.get("logs", "[]"))
            results.append(d)
        return results
    except Exception:
        return []


# ── v11: Organization Tables ─────────────────────────────────────────────────────


def save_organization(org_data: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO organizations (id, name, description, repo_count, entity_count, metadata, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
               name=excluded.name, description=excluded.description,
               repo_count=excluded.repo_count, entity_count=excluded.entity_count,
               metadata=excluded.metadata, updated_at=excluded.updated_at""",
            (
                org_data["id"],
                org_data.get("name", ""),
                org_data.get("description", ""),
                org_data.get("repo_count", 0),
                org_data.get("entity_count", 0),
                json.dumps(org_data.get("metadata", {})),
                org_data.get("created_at", time.time()),
                org_data.get("updated_at", time.time()),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("save_organization failed: %s", exc)


def get_organization(org_id: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM organizations WHERE id=?", (org_id,))
        r = cur.fetchone()
        if r:
            d = dict(r)
            d["metadata"] = json.loads(d.get("metadata", "{}"))
            return d
        return None
    except Exception:
        return None


def list_organizations_db(limit: int = 50) -> list[dict]:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM organizations ORDER BY created_at DESC LIMIT ?", (limit,))
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["metadata"] = json.loads(d.get("metadata", "{}"))
            results.append(d)
        return results
    except Exception:
        return []


def delete_organization(org_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM organizations WHERE id=?", (org_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_organization failed: %s", exc)
        return False


def save_repository(repo_data: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO repositories (id, org_id, name, path, category, language, url,
               description, file_count, indexed_at, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
               name=excluded.name, path=excluded.path, category=excluded.category,
               language=excluded.language, url=excluded.url, description=excluded.description,
               file_count=excluded.file_count, indexed_at=excluded.indexed_at,
               metadata=excluded.metadata""",
            (
                repo_data["id"],
                repo_data.get("org_id", ""),
                repo_data.get("name", ""),
                repo_data.get("path", ""),
                repo_data.get("category", "other"),
                repo_data.get("language", ""),
                repo_data.get("url", ""),
                repo_data.get("description", ""),
                repo_data.get("file_count", 0),
                repo_data.get("indexed_at"),
                json.dumps(repo_data.get("metadata", {})),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("save_repository failed: %s", exc)


def get_repositories(org_id: str) -> list[dict]:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM repositories WHERE org_id=? ORDER BY name", (org_id,))
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["metadata"] = json.loads(d.get("metadata", "{}"))
            results.append(d)
        return results
    except Exception:
        return []


def delete_repository(repo_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM repositories WHERE id=?", (repo_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_repository failed: %s", exc)
        return False


def save_repository_relationship(rel_data: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO repository_relationships (id, org_id, source_repo, target_repo,
               source_file, target_file, relationship, weight, verified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
               source_repo=excluded.source_repo, target_repo=excluded.target_repo,
               relationship=excluded.relationship, weight=excluded.weight""",
            (
                rel_data["id"],
                rel_data.get("org_id", ""),
                rel_data.get("source_repo", ""),
                rel_data.get("target_repo", ""),
                rel_data.get("source_file", ""),
                rel_data.get("target_file", ""),
                rel_data.get("relationship", "depends_on"),
                rel_data.get("weight", 1.0),
                1 if rel_data.get("verified", False) else 0,
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("save_repository_relationship failed: %s", exc)


def get_repository_relationships(org_id: str) -> list[dict]:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM repository_relationships WHERE org_id=?", (org_id,))
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def save_cross_repo_change(change_data: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO cross_repo_changes (id, org_id, branch_name, description, repos_affected,
               files_changed, status, pr_urls, created_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
               status=excluded.status, pr_urls=excluded.pr_urls, completed_at=excluded.completed_at""",
            (
                change_data["id"],
                change_data.get("org_id", ""),
                change_data.get("branch_name", ""),
                change_data.get("description", ""),
                json.dumps(change_data.get("repos_affected", [])),
                json.dumps(change_data.get("files_changed", [])),
                change_data.get("status", "pending"),
                json.dumps(change_data.get("pr_urls", [])),
                change_data.get("created_at", time.time()),
                change_data.get("completed_at"),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("save_cross_repo_change failed: %s", exc)


def get_cross_repo_changes(org_id: str, limit: int = 20) -> list[dict]:
    try:
        conn = _get_conn()
        cur = conn.execute(
            "SELECT * FROM cross_repo_changes WHERE org_id=? ORDER BY created_at DESC LIMIT ?",
            (org_id, limit),
        )
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["repos_affected"] = json.loads(d.get("repos_affected", "[]"))
            d["files_changed"] = json.loads(d.get("files_changed", "[]"))
            d["pr_urls"] = json.loads(d.get("pr_urls", "[]"))
            results.append(d)
        return results
    except Exception:
        return []


def save_impact_report(report_data: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO impact_reports (id, org_id, query, affected_repos, affected_files,
               impact_score, risk_level, recommendations, report_markdown, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
               query=excluded.query, affected_repos=excluded.affected_repos,
               impact_score=excluded.impact_score, risk_level=excluded.risk_level""",
            (
                report_data["id"],
                report_data.get("org_id", ""),
                report_data.get("query", ""),
                json.dumps(report_data.get("affected_repos", [])),
                json.dumps(report_data.get("affected_files", [])),
                report_data.get("impact_score", 0.0),
                report_data.get("risk_level", "low"),
                json.dumps(report_data.get("recommendations", [])),
                report_data.get("report_markdown", ""),
                report_data.get("created_at", time.time()),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("save_impact_report failed: %s", exc)


def get_impact_reports(org_id: str, limit: int = 20) -> list[dict]:
    try:
        conn = _get_conn()
        cur = conn.execute(
            "SELECT * FROM impact_reports WHERE org_id=? ORDER BY created_at DESC LIMIT ?",
            (org_id, limit),
        )
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["affected_repos"] = json.loads(d.get("affected_repos", "[]"))
            d["affected_files"] = json.loads(d.get("affected_files", "[]"))
            d["recommendations"] = json.loads(d.get("recommendations", "[]"))
            results.append(d)
        return results
    except Exception:
        return []


def delete_cross_repo_change(change_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM cross_repo_changes WHERE id=?", (change_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_cross_repo_change failed: %s", exc)
        return False


def delete_impact_report(report_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM impact_reports WHERE id=?", (report_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_impact_report failed: %s", exc)
        return False


def delete_repository_relationship(rel_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM repository_relationships WHERE id=?", (rel_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_repository_relationship failed: %s", exc)
        return False


def delete_repository_relationships_by_org(org_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM repository_relationships WHERE org_id=?", (org_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_repository_relationships_by_org failed: %s", exc)
        return False


def delete_impact_reports_by_org(org_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM impact_reports WHERE org_id=?", (org_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_impact_reports_by_org failed: %s", exc)
        return False


def delete_cross_repo_changes_by_org(org_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM cross_repo_changes WHERE org_id=?", (org_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_cross_repo_changes_by_org failed: %s", exc)
        return False


def delete_repositories_by_org(org_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM repositories WHERE org_id=?", (org_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_repositories_by_org failed: %s", exc)
        return False


def get_impact_report_by_id(report_id: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM impact_reports WHERE id=?", (report_id,))
        r = cur.fetchone()
        if r:
            d = dict(r)
            d["affected_repos"] = json.loads(d.get("affected_repos", "[]"))
            d["affected_files"] = json.loads(d.get("affected_files", "[]"))
            d["recommendations"] = json.loads(d.get("recommendations", "[]"))
            return d
        return None
    except Exception:
        return None


def get_cross_repo_change(change_id: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM cross_repo_changes WHERE id=?", (change_id,))
        r = cur.fetchone()
        if r:
            d = dict(r)
            d["repos_affected"] = json.loads(d.get("repos_affected", "[]"))
            d["files_changed"] = json.loads(d.get("files_changed", "[]"))
            d["pr_urls"] = json.loads(d.get("pr_urls", "[]"))
            return d
        return None
    except Exception:
        return None


def delete_benchmark_result(result_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM benchmark_results WHERE id=?", (result_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_benchmark_result failed: %s", exc)
        return False


# ── v11.1 Plugin & Agent SDK CRUD ─────────────────────────────────────────


def mem_save_plugin(plugin_data: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO plugins (id, name, version, author, description, plugin_type,
               source, enabled, manifest_json, permissions_json, resource_limits_json,
               checksum, installed_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
               name=excluded.name, version=excluded.version, author=excluded.author,
               description=excluded.description, plugin_type=excluded.plugin_type,
               source=excluded.source, enabled=excluded.enabled,
               manifest_json=excluded.manifest_json,
               permissions_json=excluded.permissions_json,
               resource_limits_json=excluded.resource_limits_json,
               checksum=excluded.checksum, updated_at=excluded.updated_at""",
            (
                plugin_data["id"],
                plugin_data.get("name", ""),
                plugin_data.get("version", "1.0.0"),
                plugin_data.get("author", ""),
                plugin_data.get("description", ""),
                plugin_data.get("plugin_type", "tool"),
                plugin_data.get("source", ""),
                1 if plugin_data.get("enabled") else 0,
                json.dumps(plugin_data.get("manifest_json", {})),
                json.dumps(plugin_data.get("permissions", [])),
                json.dumps(plugin_data.get("resource_limits", {})),
                plugin_data.get("checksum", ""),
                plugin_data.get("installed_at", ""),
                plugin_data.get("updated_at", ""),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("mem_save_plugin failed: %s", exc)


def mem_get_plugin(plugin_id: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM plugins WHERE id=?", (plugin_id,))
        r = cur.fetchone()
        if r:
            d = dict(r)
            d["manifest_json"] = json.loads(d.get("manifest_json", "{}"))
            d["permissions"] = json.loads(d.get("permissions_json", "[]"))
            d["resource_limits"] = json.loads(d.get("resource_limits_json", "{}"))
            return d
        return None
    except Exception:
        return None


def mem_list_plugins(plugin_type: str | None = None, enabled_only: bool = False) -> list[dict]:
    try:
        conn = _get_conn()
        query = "SELECT * FROM plugins"
        params = []
        conditions = []
        if plugin_type:
            conditions.append("plugin_type=?")
            params.append(plugin_type)
        if enabled_only:
            conditions.append("enabled=1")
            params.append(1)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY updated_at DESC"
        cur = conn.execute(query, params)
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["manifest_json"] = json.loads(d.get("manifest_json", "{}"))
            d["permissions"] = json.loads(d.get("permissions_json", "[]"))
            d["resource_limits"] = json.loads(d.get("resource_limits_json", "{}"))
            results.append(d)
        return results
    except Exception:
        return []


def mem_delete_plugin(plugin_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM plugins WHERE id=?", (plugin_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_delete_plugin failed: %s", exc)
        return False


def mem_save_marketplace_package(pkg_data: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO marketplace_packages (id, name, version, author, description,
               package_type, manifest_json, downloads, rating, rating_count,
               tags_json, published_at, updated_at, source_url, readme, compatibility, verified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
               name=excluded.name, version=excluded.version, author=excluded.author,
               description=excluded.description, package_type=excluded.package_type,
               manifest_json=excluded.manifest_json, downloads=excluded.downloads,
               rating=excluded.rating, rating_count=excluded.rating_count,
               tags_json=excluded.tags_json, updated_at=excluded.updated_at,
               source_url=excluded.source_url, readme=excluded.readme,
               compatibility=excluded.compatibility, verified=excluded.verified""",
            (
                pkg_data["id"],
                pkg_data.get("name", ""),
                pkg_data.get("version", "1.0.0"),
                pkg_data.get("author", ""),
                pkg_data.get("description", ""),
                pkg_data.get("package_type", "plugin"),
                json.dumps(pkg_data.get("manifest_json", {})),
                pkg_data.get("downloads", 0),
                pkg_data.get("rating", 0.0),
                pkg_data.get("rating_count", 0),
                json.dumps(pkg_data.get("tags", [])),
                pkg_data.get("published_at", ""),
                pkg_data.get("updated_at", ""),
                pkg_data.get("source_url", ""),
                pkg_data.get("readme", ""),
                pkg_data.get("compatibility", ">=11.0.0"),
                1 if pkg_data.get("verified") else 0,
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("mem_save_marketplace_package failed: %s", exc)


def mem_get_marketplace_package(package_id: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM marketplace_packages WHERE id=?", (package_id,))
        r = cur.fetchone()
        if r:
            d = dict(r)
            d["manifest_json"] = json.loads(d.get("manifest_json", "{}"))
            d["tags"] = json.loads(d.get("tags_json", "[]"))
            return d
        return None
    except Exception:
        return None


def mem_search_marketplace_packages(query: str = "", package_type: str | None = None, limit: int = 50) -> list[dict]:
    try:
        conn = _get_conn()
        sql = "SELECT * FROM marketplace_packages WHERE 1=1"
        params = []
        if query:
            sql += " AND (name LIKE ? OR description LIKE ? OR author LIKE ?)"
            q = f"%{query}%"
            params.extend([q, q, q])
        if package_type:
            sql += " AND package_type=?"
            params.append(package_type)
        sql += " ORDER BY downloads DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(sql, params)
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["manifest_json"] = json.loads(d.get("manifest_json", "{}"))
            d["tags"] = json.loads(d.get("tags_json", "[]"))
            results.append(d)
        return results
    except Exception:
        return []


def mem_delete_marketplace_package(package_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM marketplace_packages WHERE id=?", (package_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_delete_marketplace_package failed: %s", exc)
        return False


def mem_save_custom_agent(agent_data: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO custom_agents (id, name, version, description, source,
               capabilities_json, hooks_json, config_json, enabled, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
               name=excluded.name, version=excluded.version, description=excluded.description,
               source=excluded.source, capabilities_json=excluded.capabilities_json,
               hooks_json=excluded.hooks_json, config_json=excluded.config_json,
               enabled=excluded.enabled, updated_at=excluded.updated_at""",
            (
                agent_data["id"],
                agent_data.get("name", ""),
                agent_data.get("version", "1.0.0"),
                agent_data.get("description", ""),
                agent_data.get("source", ""),
                json.dumps(agent_data.get("capabilities", [])),
                json.dumps(agent_data.get("hooks", {})),
                json.dumps(agent_data.get("config", {})),
                1 if agent_data.get("enabled") else 0,
                agent_data.get("created_at", ""),
                agent_data.get("updated_at", ""),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("mem_save_custom_agent failed: %s", exc)


def mem_list_custom_agents(enabled_only: bool = False) -> list[dict]:
    try:
        conn = _get_conn()
        query = "SELECT * FROM custom_agents"
        params = []
        if enabled_only:
            query += " WHERE enabled=1"
            params.append(1)
        query += " ORDER BY updated_at DESC"
        cur = conn.execute(query, params)
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["capabilities"] = json.loads(d.get("capabilities_json", "[]"))
            d["hooks"] = json.loads(d.get("hooks_json", "{}"))
            d["config"] = json.loads(d.get("config_json", "{}"))
            results.append(d)
        return results
    except Exception:
        return []


def mem_delete_custom_agent(agent_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM custom_agents WHERE id=?", (agent_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_delete_custom_agent failed: %s", exc)
        return False


def mem_save_custom_workflow(workflow_data: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO custom_workflows (id, name, version, description, source,
               steps_json, status, config_json, enabled, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
               name=excluded.name, version=excluded.version, description=excluded.description,
               source=excluded.source, steps_json=excluded.steps_json,
               status=excluded.status, config_json=excluded.config_json,
               enabled=excluded.enabled, updated_at=excluded.updated_at""",
            (
                workflow_data["id"],
                workflow_data.get("name", ""),
                workflow_data.get("version", "1.0.0"),
                workflow_data.get("description", ""),
                workflow_data.get("source", ""),
                json.dumps(workflow_data.get("steps", [])),
                workflow_data.get("status", "pending"),
                json.dumps(workflow_data.get("config", {})),
                1 if workflow_data.get("enabled") else 0,
                workflow_data.get("created_at", ""),
                workflow_data.get("updated_at", ""),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("mem_save_custom_workflow failed: %s", exc)


def mem_list_custom_workflows(enabled_only: bool = False) -> list[dict]:
    try:
        conn = _get_conn()
        query = "SELECT * FROM custom_workflows"
        params = []
        if enabled_only:
            query += " WHERE enabled=1"
            params.append(1)
        query += " ORDER BY updated_at DESC"
        cur = conn.execute(query, params)
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["steps"] = json.loads(d.get("steps_json", "[]"))
            d["config"] = json.loads(d.get("config_json", "{}"))
            results.append(d)
        return results
    except Exception:
        return []


def mem_delete_custom_workflow(workflow_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM custom_workflows WHERE id=?", (workflow_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_delete_custom_workflow failed: %s", exc)
        return False


# ===== v12.0 Autonomous Evaluation CRUD =====


def mem_save_evaluation_run(run: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO evaluation_runs
               (id, trigger_type, status, autonomy_score, success_rate,
                total_cost, total_runtime, healing_rate, deployment_success_rate,
                benchmark_score, tasks_completed, tasks_failed, error_log,
                started_at, completed_at, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run["id"],
                run.get("trigger_type", "on_demand"),
                run.get("status", "pending"),
                run.get("autonomy_score", 0.0),
                run.get("success_rate", 0.0),
                run.get("total_cost", 0.0),
                run.get("total_runtime", 0.0),
                run.get("healing_rate", 0.0),
                run.get("deployment_success_rate", 0.0),
                run.get("benchmark_score", 0.0),
                run.get("tasks_completed", 0),
                run.get("tasks_failed", 0),
                run.get("error_log", ""),
                run.get("started_at"),
                run.get("completed_at"),
                run.get("created_at"),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("mem_save_evaluation_run failed: %s", exc)


def mem_get_evaluation_run(run_id: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM evaluation_runs WHERE id=?", (run_id,))
        r = cur.fetchone()
        return dict(r) if r else None
    except Exception:
        return None


def mem_list_evaluation_runs(limit: int = 50, trigger_type: str | None = None, status: str | None = None) -> list[dict]:
    try:
        conn = _get_conn()
        conditions = []
        params = []
        if trigger_type:
            conditions.append("trigger_type=?")
            params.append(trigger_type)
        if status:
            conditions.append("status=?")
            params.append(status)
        query = "SELECT * FROM evaluation_runs"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def mem_save_evaluation_report(report: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO evaluation_reports
               (id, report_type, title, summary, metrics_json, trends_json,
                regressions_found, improvements_found, recommendations,
                report_markdown, period_start, period_end, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                report["id"],
                report.get("report_type", "daily"),
                report.get("title", ""),
                report.get("summary", ""),
                json.dumps(report.get("metrics", {})),
                json.dumps(report.get("trends", {})),
                json.dumps(report.get("regressions_found", [])),
                json.dumps(report.get("improvements_found", [])),
                json.dumps(report.get("recommendations", [])),
                report.get("report_markdown", ""),
                report.get("period_start"),
                report.get("period_end"),
                report.get("created_at"),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("mem_save_evaluation_report failed: %s", exc)


def mem_get_evaluation_report(report_id: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM evaluation_reports WHERE id=?", (report_id,))
        r = cur.fetchone()
        if r:
            d = dict(r)
            d["metrics"] = json.loads(d.get("metrics_json", "{}"))
            d["trends"] = json.loads(d.get("trends_json", "{}"))
            d["regressions_found"] = json.loads(d.get("regressions_found", "[]"))
            d["improvements_found"] = json.loads(d.get("improvements_found", "[]"))
            d["recommendations"] = json.loads(d.get("recommendations", "[]"))
            return d
        return None
    except Exception:
        return None


def mem_list_evaluation_reports(report_type: str | None = None, limit: int = 20) -> list[dict]:
    try:
        conn = _get_conn()
        if report_type:
            cur = conn.execute(
                "SELECT * FROM evaluation_reports WHERE report_type=? ORDER BY created_at DESC LIMIT ?",
                (report_type, limit),
            )
        else:
            cur = conn.execute("SELECT * FROM evaluation_reports ORDER BY created_at DESC LIMIT ?", (limit,))
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["metrics"] = json.loads(d.get("metrics_json", "{}"))
            d["trends"] = json.loads(d.get("trends_json", "{}"))
            d["regressions_found"] = json.loads(d.get("regressions_found", "[]"))
            d["improvements_found"] = json.loads(d.get("improvements_found", "[]"))
            d["recommendations"] = json.loads(d.get("recommendations", "[]"))
            results.append(d)
        return results
    except Exception:
        return []


def mem_save_regression(regression: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO regressions
               (id, category, severity, metric, previous_value, current_value,
                change_pct, title, description, dismissed, run_id, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                regression["id"],
                regression.get("category", "general"),
                regression.get("severity", "low"),
                regression.get("metric", ""),
                regression.get("previous_value", 0.0),
                regression.get("current_value", 0.0),
                regression.get("change_pct", 0.0),
                regression.get("title", ""),
                regression.get("description", ""),
                1 if regression.get("dismissed") else 0,
                regression.get("run_id", ""),
                regression.get("created_at"),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("mem_save_regression failed: %s", exc)


def mem_list_regressions(
    category: str | None = None, severity: str | None = None, dismissed: bool | None = None, limit: int = 100
) -> list[dict]:
    try:
        conn = _get_conn()
        conditions = []
        params = []
        if category:
            conditions.append("category=?")
            params.append(category)
        if severity:
            conditions.append("severity=?")
            params.append(severity)
        if dismissed is not None:
            conditions.append("dismissed=?")
            params.append(1 if dismissed else 0)
        query = "SELECT * FROM regressions"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def mem_get_regression(regression_id: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM regressions WHERE id=?", (regression_id,))
        r = cur.fetchone()
        return dict(r) if r else None
    except Exception:
        return None


def mem_update_regression(regression_id: str, updates: dict) -> bool:
    try:
        conn = _get_conn()
        fields = []
        params = []
        for key in ("dismissed", "severity", "description"):
            if key in updates:
                if key == "dismissed":
                    fields.append(f"{key}=?")
                    params.append(1 if updates[key] else 0)
                else:
                    fields.append(f"{key}=?")
                    params.append(updates[key])
        if not fields:
            return False
        params.append(regression_id)
        conn.execute(f"UPDATE regressions SET {', '.join(fields)} WHERE id=?", params)
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_update_regression failed: %s", exc)
        return False


def mem_save_leaderboard_entry(entry: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO leaderboards
               (id, category, entry_name, score, autonomy_score,
                reliability_score, cost_efficiency, run_count,
                metadata_json, last_updated)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                entry["id"],
                entry.get("category", "general"),
                entry.get("entry_name", ""),
                entry.get("score", 0.0),
                entry.get("autonomy_score", 0.0),
                entry.get("reliability_score", 0.0),
                entry.get("cost_efficiency", 0.0),
                entry.get("run_count", 1),
                json.dumps(entry.get("metadata", {})),
                entry.get("last_updated"),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("mem_save_leaderboard_entry failed: %s", exc)


def mem_get_leaderboard(category: str | None = None, sort_by: str = "score", limit: int = 20) -> list[dict]:
    try:
        conn = _get_conn()
        valid_sorts = {"score", "autonomy_score", "reliability_score", "cost_efficiency", "run_count"}
        if sort_by not in valid_sorts:
            sort_by = "score"
        if category:
            cur = conn.execute(
                f"SELECT * FROM leaderboards WHERE category=? ORDER BY {sort_by} DESC LIMIT ?", (category, limit)
            )
        else:
            cur = conn.execute(f"SELECT * FROM leaderboards ORDER BY {sort_by} DESC LIMIT ?", (limit,))
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["metadata"] = json.loads(d.get("metadata_json", "{}"))
            results.append(d)
        return results
    except Exception:
        return []


def mem_get_leaderboard_entry(entry_id: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM leaderboards WHERE id=?", (entry_id,))
        r = cur.fetchone()
        if r:
            d = dict(r)
            d["metadata"] = json.loads(d.get("metadata_json", "{}"))
            return d
        return None
    except Exception:
        return None


def mem_delete_leaderboard_entry(entry_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM leaderboards WHERE id=?", (entry_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_delete_leaderboard_entry failed: %s", exc)
        return False


def mem_get_leaderboard_categories() -> list[str]:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT DISTINCT category FROM leaderboards ORDER BY category")
        return [r["category"] for r in cur.fetchall()]
    except Exception:
        return []


def mem_save_version_snapshot(snapshot: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO version_history
               (id, version, snapshot_data, snapshot_type, created_at)
               VALUES (?,?,?,?,?)""",
            (
                snapshot["id"],
                snapshot.get("version", ""),
                json.dumps(snapshot.get("data", {})),
                snapshot.get("snapshot_type", "full"),
                snapshot.get("created_at"),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("mem_save_version_snapshot failed: %s", exc)


def mem_get_version_snapshots(version: str | None = None, limit: int = 50) -> list[dict]:
    try:
        conn = _get_conn()
        if version:
            cur = conn.execute(
                "SELECT * FROM version_history WHERE version=? ORDER BY created_at DESC LIMIT ?", (version, limit)
            )
        else:
            cur = conn.execute("SELECT * FROM version_history ORDER BY created_at DESC LIMIT ?", (limit,))
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["data"] = json.loads(d.get("snapshot_data", "{}"))
            results.append(d)
        return results
    except Exception:
        return []


def mem_save_version_comparison(comparison: dict) -> None:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO version_comparisons
               (id, from_version, to_version, deltas, summary, created_at)
               VALUES (?,?,?,?,?,?)""",
            (
                comparison["id"],
                comparison.get("from_version", ""),
                comparison.get("to_version", ""),
                json.dumps(comparison.get("deltas", {})),
                comparison.get("summary", ""),
                comparison.get("created_at"),
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.warning("mem_save_version_comparison failed: %s", exc)
        return None


def mem_get_version_comparisons(
    from_version: str | None = None, to_version: str | None = None, limit: int = 20
) -> list[dict]:
    try:
        conn = _get_conn()
        conditions = []
        params = []
        if from_version:
            conditions.append("from_version=?")
            params.append(from_version)
        if to_version:
            conditions.append("to_version=?")
            params.append(to_version)
        query = "SELECT * FROM version_comparisons"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(query, params)
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["deltas"] = json.loads(d.get("deltas", "{}"))
            results.append(d)
        return results
    except Exception:
        return []


# ── v12 Phase 4 — Scheduler Metadata CRUD ──────────────────────────────────────


def mem_save_scheduler_metadata(meta: dict) -> bool:
    try:
        conn = _get_conn()
        # Delete any existing row with the same schedule_type to avoid duplicates
        conn.execute("DELETE FROM scheduler_metadata WHERE schedule_type=?", (meta.get("schedule_type", "nightly"),))
        conn.execute(
            """INSERT INTO scheduler_metadata
               (id, schedule_type, enabled, interval_hours, window_start_utc,
                day_of_week, execution_time_utc, domain_timeout_seconds,
                parallel_execution, last_run_at, next_run_at,
                recovery_window_hours, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                meta["id"],
                meta.get("schedule_type", "nightly"),
                meta.get("enabled", 1),
                meta.get("interval_hours", 24.0),
                meta.get("window_start_utc", "02:00"),
                meta.get("day_of_week", 0),
                meta.get("execution_time_utc", "02:00"),
                meta.get("domain_timeout_seconds", 300.0),
                1 if meta.get("parallel_execution") else 0,
                meta.get("last_run_at"),
                meta.get("next_run_at"),
                meta.get("recovery_window_hours", 6.0),
                meta.get("created_at"),
                meta.get("updated_at"),
            ),
        )
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_save_scheduler_metadata failed: %s", exc)
        return False


def mem_get_scheduler_metadata(schedule_type: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM scheduler_metadata WHERE schedule_type=?", (schedule_type,))
        r = cur.fetchone()
        return dict(r) if r else None
    except Exception:
        return None


def mem_list_scheduler_metadata(enabled_only: bool = False) -> list[dict]:
    try:
        conn = _get_conn()
        if enabled_only:
            cur = conn.execute("SELECT * FROM scheduler_metadata WHERE enabled=1 ORDER BY schedule_type")
        else:
            cur = conn.execute("SELECT * FROM scheduler_metadata ORDER BY schedule_type")
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def mem_delete_scheduler_metadata(schedule_type: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM scheduler_metadata WHERE schedule_type=?", (schedule_type,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_delete_scheduler_metadata failed: %s", exc)
        return False


def mem_update_evaluation_run(run_id: str, updates: dict) -> bool:
    try:
        conn = _get_conn()
        allowed = {
            "status",
            "autonomy_score",
            "success_rate",
            "total_cost",
            "total_runtime",
            "healing_rate",
            "deployment_success_rate",
            "benchmark_score",
            "error_log",
            "completed_at",
        }
        fields = []
        params = []
        for key, val in updates.items():
            if key in allowed:
                fields.append(f"{key}=?")
                params.append(val)
        if not fields:
            return False
        params.append(run_id)
        conn.execute(f"UPDATE evaluation_runs SET {', '.join(fields)} WHERE id=?", params)
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_update_evaluation_run failed: %s", exc)
        return False


def mem_count_evaluation_runs() -> int:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT COUNT(*) AS cnt FROM evaluation_runs")
        r = cur.fetchone()
        return r["cnt"] if r else 0
    except Exception:
        return 0


def mem_count_missed_runs(schedule_type: str, since_timestamp: float) -> int:
    try:
        conn = _get_conn()
        cur = conn.execute(
            "SELECT COUNT(*) AS cnt FROM evaluation_runs WHERE trigger_type=? AND created_at >= ?",
            (schedule_type, since_timestamp),
        )
        r = cur.fetchone()
        return r["cnt"] if r else 0
    except Exception:
        return 0


# ── v12.5 — Learning Engine Feedback Loop CRUD ──────────────────────────────


def mem_save_learning_feedback(fb: dict) -> bool:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO learning_feedback
               (id, feedback_type, source, category, score, metric_name,
                metric_value, context_json, run_id, version, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                fb["id"],
                fb.get("feedback_type", "evaluation"),
                fb.get("source", ""),
                fb.get("category", "general"),
                fb.get("score", 0.0),
                fb.get("metric_name", ""),
                fb.get("metric_value", 0.0),
                json.dumps(fb.get("context", {})),
                fb.get("run_id", ""),
                fb.get("version", ""),
                fb.get("created_at"),
            ),
        )
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_save_learning_feedback failed: %s", exc)
        return False


def mem_list_learning_feedback(
    feedback_type: str | None = None,
    category: str | None = None,
    limit: int = 100,
) -> list[dict]:
    try:
        conn = _get_conn()
        conditions = []
        params = []
        if feedback_type:
            conditions.append("feedback_type=?")
            params.append(feedback_type)
        if category:
            conditions.append("category=?")
            params.append(category)
        query = "SELECT * FROM learning_feedback"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(query, params)
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def mem_save_learning_pattern(pattern: dict) -> bool:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO learning_feedback_patterns
               (id, pattern_type, category, title, description, strategy,
                outcome, success_count, failure_count, confidence, tags,
                source_run_ids, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                pattern["id"],
                pattern.get("pattern_type", "strategy"),
                pattern.get("category", "general"),
                pattern.get("title", ""),
                pattern.get("description", ""),
                pattern.get("strategy", ""),
                pattern.get("outcome", ""),
                pattern.get("success_count", 0),
                pattern.get("failure_count", 0),
                pattern.get("confidence", 0.0),
                json.dumps(pattern.get("tags", [])),
                json.dumps(pattern.get("source_run_ids", [])),
                pattern.get("created_at"),
                pattern.get("updated_at"),
            ),
        )
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_save_learning_pattern failed: %s", exc)
        return False


def mem_get_learning_pattern(pattern_id: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM learning_feedback_patterns WHERE id=?", (pattern_id,))
        r = cur.fetchone()
        if r:
            d = dict(r)
            d["tags"] = json.loads(d.get("tags", "[]"))
            d["source_run_ids"] = json.loads(d.get("source_run_ids", "[]"))
            return d
        return None
    except Exception:
        return None


def mem_list_learning_patterns(
    pattern_type: str | None = None,
    category: str | None = None,
    min_confidence: float = 0.0,
    limit: int = 100,
) -> list[dict]:
    try:
        conn = _get_conn()
        conditions = []
        params = []
        if pattern_type:
            conditions.append("pattern_type=?")
            params.append(pattern_type)
        if category:
            conditions.append("category=?")
            params.append(category)
        if min_confidence > 0:
            conditions.append("confidence>=?")
            params.append(min_confidence)
        query = "SELECT * FROM learning_feedback_patterns"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY confidence DESC, created_at DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(query, params)
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["tags"] = json.loads(d.get("tags", "[]"))
            d["source_run_ids"] = json.loads(d.get("source_run_ids", "[]"))
            results.append(d)
        return results
    except Exception:
        return []


def mem_save_learning_recommendation(rec: dict) -> bool:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT INTO learning_feedback_recommendations
               (id, recommendation_type, category, title, description,
                priority, rationale, expected_impact,
                implementation_suggestions, status,
                source_pattern_ids, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                rec["id"],
                rec.get("recommendation_type", "architecture"),
                rec.get("category", "general"),
                rec.get("title", ""),
                rec.get("description", ""),
                rec.get("priority", "medium"),
                rec.get("rationale", ""),
                rec.get("expected_impact", ""),
                rec.get("implementation_suggestions", ""),
                rec.get("status", "active"),
                json.dumps(rec.get("source_pattern_ids", [])),
                rec.get("created_at"),
                rec.get("updated_at"),
            ),
        )
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_save_learning_recommendation failed: %s", exc)
        return False


def mem_get_learning_recommendation(rec_id: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM learning_feedback_recommendations WHERE id=?", (rec_id,))
        r = cur.fetchone()
        if r:
            d = dict(r)
            d["source_pattern_ids"] = json.loads(d.get("source_pattern_ids", "[]"))
            return d
        return None
    except Exception:
        return None


def mem_list_learning_recommendations(
    recommendation_type: str | None = None,
    category: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    try:
        conn = _get_conn()
        conditions = []
        params = []
        if recommendation_type:
            conditions.append("recommendation_type=?")
            params.append(recommendation_type)
        if category:
            conditions.append("category=?")
            params.append(category)
        if status:
            conditions.append("status=?")
            params.append(status)
        query = "SELECT * FROM learning_feedback_recommendations"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(query, params)
        results = []
        for r in cur.fetchall():
            d = dict(r)
            d["source_pattern_ids"] = json.loads(d.get("source_pattern_ids", "[]"))
            results.append(d)
        return results
    except Exception:
        return []


def mem_get_learning_insights(
    category: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Aggregate learning insights from feedback, patterns, and recommendations."""
    try:
        insights = []
        conn = _get_conn()

        # High-confidence patterns
        pattern_conditions = []
        pattern_params = []
        if category:
            pattern_conditions.append("category=?")
            pattern_params.append(category)
        pattern_query = "SELECT * FROM learning_feedback_patterns"
        if pattern_conditions:
            pattern_query += " WHERE " + " AND ".join(pattern_conditions)
        pattern_query += " ORDER BY confidence DESC LIMIT ?"
        pattern_params.append(limit)
        for r in conn.execute(pattern_query, pattern_params).fetchall():
            d = dict(r)
            d["insight_type"] = "pattern"
            d["tags"] = json.loads(d.get("tags", "[]"))
            insights.append(d)

        # Active recommendations
        rec_conditions = ["status=?"]
        rec_params = ["active"]
        if category:
            rec_conditions.append("category=?")
            rec_params.append(category)
        rec_query = "SELECT * FROM learning_feedback_recommendations WHERE " + " AND ".join(rec_conditions)
        rec_query += " ORDER BY created_at DESC LIMIT ?"
        rec_params.append(limit)
        for r in conn.execute(rec_query, rec_params).fetchall():
            d = dict(r)
            d["insight_type"] = "recommendation"
            d["source_pattern_ids"] = json.loads(d.get("source_pattern_ids", "[]"))
            insights.append(d)

        # Feedback averages by category
        fb_conditions = []
        fb_params = []
        if category:
            fb_conditions.append("category=?")
            fb_params.append(category)
        fb_query = "SELECT category, COUNT(*) AS count, AVG(score) AS avg_score FROM learning_feedback"
        if fb_conditions:
            fb_query += " WHERE " + " AND ".join(fb_conditions)
        fb_query += " GROUP BY category ORDER BY avg_score DESC"
        for r in conn.execute(fb_query, fb_params).fetchall():
            insights.append(
                {
                    "insight_type": "feedback_summary",
                    "category": r["category"],
                    "feedback_count": r["count"],
                    "average_score": r["avg_score"],
                }
            )

        insights.sort(key=lambda x: x.get("confidence", 0) if x.get("insight_type") == "pattern" else 0, reverse=True)
        return insights[:limit]
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════════
# Campaign CRUD
# ═══════════════════════════════════════════════════════════════════════════


def mem_save_campaign(campaign: dict) -> bool:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO campaigns
               (id, name, status, config, total_runs, completed_runs, failed_runs,
                domains, created_at, started_at, completed_at, error)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                campaign["id"],
                campaign.get("name", ""),
                campaign.get("status", "pending"),
                json.dumps(campaign.get("config", {})),
                campaign.get("total_runs", 0),
                campaign.get("completed_runs", 0),
                campaign.get("failed_runs", 0),
                json.dumps(campaign.get("domains", [])),
                campaign.get("created_at", 0),
                campaign.get("started_at"),
                campaign.get("completed_at"),
                campaign.get("error", ""),
            ),
        )
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_save_campaign failed: %s", exc)
        return False


def mem_get_campaign(campaign_id: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM campaigns WHERE id=?", (campaign_id,))
        row = cur.fetchone()
        if row is None:
            return None
        d = dict(row)
        d["config"] = json.loads(d.get("config", "{}"))
        d["domains"] = json.loads(d.get("domains", "[]"))
        return d
    except Exception as exc:
        logger.warning("mem_get_campaign failed: %s", exc)
        return None


def mem_list_campaigns(limit: int = 50, status: str | None = None) -> list[dict]:
    try:
        conn = _get_conn()
        conditions = []
        params = []
        if status:
            conditions.append("status=?")
            params.append(status)
        query = "SELECT * FROM campaigns"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cur = conn.execute(query, params)
        results = []
        for row in cur.fetchall():
            d = dict(row)
            d["config"] = json.loads(d.get("config", "{}"))
            d["domains"] = json.loads(d.get("domains", "[]"))
            results.append(d)
        return results
    except Exception as exc:
        logger.warning("mem_list_campaigns failed: %s", exc)
        return []


def mem_update_campaign(campaign_id: str, updates: dict) -> bool:
    try:
        conn = _get_conn()
        allowed = {
            "status",
            "total_runs",
            "completed_runs",
            "failed_runs",
            "started_at",
            "completed_at",
            "error",
            "domains",
        }
        fields = []
        params = []
        for key, val in updates.items():
            if key in allowed:
                if key == "domains":
                    val = json.dumps(val)
                fields.append(f"{key}=?")
                params.append(val)
        if not fields:
            return False
        params.append(campaign_id)
        conn.execute(f"UPDATE campaigns SET {', '.join(fields)} WHERE id=?", params)
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_update_campaign failed: %s", exc)
        return False


def mem_delete_campaign(campaign_id: str) -> bool:
    try:
        conn = _get_conn()
        conn.execute("DELETE FROM campaign_runs WHERE campaign_id=?", (campaign_id,))
        conn.execute("DELETE FROM campaigns WHERE id=?", (campaign_id,))
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_delete_campaign failed: %s", exc)
        return False


# ── Campaign Runs ────────────────────────────────────────────────────────────


def mem_save_campaign_run(run: dict) -> bool:
    try:
        conn = _get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO campaign_runs
               (id, campaign_id, domain, iteration, status,
                autonomy_score, execution_time, cost,
                tests_generated, tests_passed,
                healing_iterations, deployment_success, benchmark_success,
                error, created_at, completed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run["id"],
                run["campaign_id"],
                run["domain"],
                run.get("iteration", 1),
                run.get("status", "pending"),
                run.get("autonomy_score", 0.0),
                run.get("execution_time", 0.0),
                run.get("cost", 0.0),
                run.get("tests_generated", 0),
                run.get("tests_passed", 0),
                run.get("healing_iterations", 0),
                1 if run.get("deployment_success") else 0,
                1 if run.get("benchmark_success") else 0,
                run.get("error", ""),
                run.get("created_at", 0),
                run.get("completed_at"),
            ),
        )
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_save_campaign_run failed: %s", exc)
        return False


def mem_get_campaign_run(run_id: str) -> dict | None:
    try:
        conn = _get_conn()
        cur = conn.execute("SELECT * FROM campaign_runs WHERE id=?", (run_id,))
        row = cur.fetchone()
        if row is None:
            return None
        d = dict(row)
        d["deployment_success"] = bool(d["deployment_success"])
        d["benchmark_success"] = bool(d["benchmark_success"])
        return d
    except Exception as exc:
        logger.warning("mem_get_campaign_run failed: %s", exc)
        return None


def mem_list_campaign_runs(
    campaign_id: str | None = None,
    domain: str | None = None,
    status: str | None = None,
    limit: int = 500,
) -> list[dict]:
    try:
        conn = _get_conn()
        conditions = []
        params = []
        if campaign_id:
            conditions.append("campaign_id=?")
            params.append(campaign_id)
        if domain:
            conditions.append("domain=?")
            params.append(domain)
        if status:
            conditions.append("status=?")
            params.append(status)
        query = "SELECT * FROM campaign_runs"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)
        cur = conn.execute(query, params)
        results = []
        for row in cur.fetchall():
            d = dict(row)
            d["deployment_success"] = bool(d["deployment_success"])
            d["benchmark_success"] = bool(d["benchmark_success"])
            results.append(d)
        return results
    except Exception as exc:
        logger.warning("mem_list_campaign_runs failed: %s", exc)
        return []


def mem_update_campaign_run(run_id: str, updates: dict) -> bool:
    try:
        conn = _get_conn()
        allowed = {
            "status",
            "autonomy_score",
            "execution_time",
            "cost",
            "tests_generated",
            "tests_passed",
            "healing_iterations",
            "deployment_success",
            "benchmark_success",
            "error",
            "completed_at",
        }
        fields = []
        params = []
        for key, val in updates.items():
            if key in allowed:
                if key in ("deployment_success", "benchmark_success"):
                    val = 1 if val else 0
                fields.append(f"{key}=?")
                params.append(val)
        if not fields:
            return False
        params.append(run_id)
        conn.execute(f"UPDATE campaign_runs SET {', '.join(fields)} WHERE id=?", params)
        conn.commit()
        return True
    except Exception as exc:
        logger.warning("mem_update_campaign_run failed: %s", exc)
        return False


def mem_count_campaign_runs(campaign_id: str | None = None, status: str | None = None) -> int:
    try:
        conn = _get_conn()
        conditions = []
        params = []
        if campaign_id:
            conditions.append("campaign_id=?")
            params.append(campaign_id)
        if status:
            conditions.append("status=?")
            params.append(status)
        query = "SELECT COUNT(*) AS cnt FROM campaign_runs"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        cur = conn.execute(query, params)
        row = cur.fetchone()
        return row["cnt"] if row else 0
    except Exception:
        return 0
