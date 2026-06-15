from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


SQLITE_COLUMN_DEFAULTS: dict[str, dict[str, str]] = {
    "projects": {
        "target_words": "INTEGER NOT NULL DEFAULT 0",
        "current_volume": "INTEGER NOT NULL DEFAULT 1",
        "current_chapter": "INTEGER NOT NULL DEFAULT 1",
        "cover_image": "TEXT NOT NULL DEFAULT ''",
        "initial_idea": "TEXT NOT NULL DEFAULT ''",
    },
    "characters": {
        "aliases_json": "TEXT NOT NULL DEFAULT '[]'",
        "role_type": "TEXT NOT NULL DEFAULT 'supporting'",
        "importance_level": "TEXT NOT NULL DEFAULT 'medium'",
        "importance_score": "INTEGER NOT NULL DEFAULT 50",
        "summary": "TEXT NOT NULL DEFAULT ''",
        "appearance": "TEXT NOT NULL DEFAULT ''",
        "personality": "TEXT NOT NULL DEFAULT ''",
        "goals_json": "TEXT NOT NULL DEFAULT '[]'",
        "motivations_json": "TEXT NOT NULL DEFAULT '[]'",
        "secrets_json": "TEXT NOT NULL DEFAULT '[]'",
        "abilities_json": "TEXT NOT NULL DEFAULT '[]'",
        "weaknesses_json": "TEXT NOT NULL DEFAULT '[]'",
        "character_arc": "TEXT NOT NULL DEFAULT ''",
        "current_status": "TEXT NOT NULL DEFAULT 'active'",
        "first_appearance_chapter_id": "TEXT",
        "last_seen_chapter_id": "TEXT",
        "related_entity_ids_json": "TEXT NOT NULL DEFAULT '[]'",
        "related_character_ids_json": "TEXT NOT NULL DEFAULT '[]'",
        "updated_reason": "TEXT NOT NULL DEFAULT ''",
        "source": "TEXT NOT NULL DEFAULT 'manual'",
    },
    "chapters": {
        "pov_character": "TEXT NOT NULL DEFAULT ''",
        "core_event": "TEXT NOT NULL DEFAULT ''",
        "conflict": "TEXT NOT NULL DEFAULT ''",
        "turn_point": "TEXT NOT NULL DEFAULT ''",
        "emotional_beats_json": "TEXT NOT NULL DEFAULT '[]'",
        "plot_purpose": "TEXT NOT NULL DEFAULT ''",
        "cliffhanger": "TEXT NOT NULL DEFAULT ''",
        "final_text": "TEXT NOT NULL DEFAULT ''",
        "summary": "TEXT NOT NULL DEFAULT ''",
        "sort_order": "INTEGER NOT NULL DEFAULT 0",
        "is_locked": "INTEGER NOT NULL DEFAULT 0",
        "deleted_at": "DATETIME",
    },
    "generation_jobs": {
        "current_agent": "TEXT NOT NULL DEFAULT ''",
        "langsmith_run_id": "TEXT NOT NULL DEFAULT ''",
        "langsmith_url": "TEXT NOT NULL DEFAULT ''",
        "trace_mode": "TEXT NOT NULL DEFAULT 'local'",
    },
    "agent_runs": {
        "langsmith_run_id": "TEXT NOT NULL DEFAULT ''",
        "langsmith_url": "TEXT NOT NULL DEFAULT ''",
        "trace_mode": "TEXT NOT NULL DEFAULT 'local'",
    },
    "foreshadowing_items": {
        "planted_chapter_id": "TEXT",
        "planned_payoff_chapter_id": "TEXT",
        "actual_payoff_chapter_id": "TEXT",
        "importance_level": "TEXT NOT NULL DEFAULT 'medium'",
        "related_character_ids_json": "TEXT NOT NULL DEFAULT '[]'",
        "related_entity_ids_json": "TEXT NOT NULL DEFAULT '[]'",
        "source": "TEXT NOT NULL DEFAULT 'manual'",
    },
}

SQLITE_TABLE_DEFAULTS: dict[str, str] = {
    "agent_model_configs": """
        CREATE TABLE agent_model_configs (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            CONSTRAINT uq_agent_model_workflow_agent UNIQUE (workflow_id, agent_name)
        )
    """,
    "runtime_settings": """
        CREATE TABLE runtime_settings (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL DEFAULT 'null',
            updated_at DATETIME NOT NULL
        )
    """,
    "deep_agent_sessions": """
        CREATE TABLE deep_agent_sessions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            mode TEXT NOT NULL DEFAULT 'advisor',
            status TEXT NOT NULL DEFAULT 'active',
            objective TEXT NOT NULL DEFAULT '',
            privacy_mode TEXT NOT NULL DEFAULT 'metadata_only',
            summary TEXT NOT NULL DEFAULT '',
            state_json TEXT NOT NULL DEFAULT '{}',
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """,
    "deep_agent_tool_calls": """
        CREATE TABLE deep_agent_tool_calls (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_approval',
            risk_level TEXT NOT NULL DEFAULT 'medium',
            requires_approval INTEGER NOT NULL DEFAULT 1,
            arguments_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT NOT NULL DEFAULT '{}',
            created_at DATETIME NOT NULL,
            approved_at DATETIME,
            rejected_at DATETIME,
            executed_at DATETIME,
            FOREIGN KEY(session_id) REFERENCES deep_agent_sessions(id) ON DELETE CASCADE,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """,
    "langsmith_trace_links": """
        CREATE TABLE langsmith_trace_links (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            job_id TEXT,
            agent_run_id TEXT,
            session_id TEXT,
            trace_mode TEXT NOT NULL DEFAULT 'metadata_only',
            langsmith_run_id TEXT NOT NULL DEFAULT '',
            langsmith_url TEXT NOT NULL DEFAULT '',
            payload_policy TEXT NOT NULL DEFAULT 'metadata_only',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at DATETIME NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(job_id) REFERENCES generation_jobs(id) ON DELETE CASCADE,
            FOREIGN KEY(agent_run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
            FOREIGN KEY(session_id) REFERENCES deep_agent_sessions(id) ON DELETE SET NULL
        )
    """,
    "canon_nodes": """
        CREATE TABLE canon_nodes (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            parent_id TEXT,
            node_type TEXT NOT NULL DEFAULT 'item',
            ref_type TEXT NOT NULL DEFAULT 'folder',
            ref_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active',
            importance_level TEXT NOT NULL DEFAULT 'medium',
            activity_status TEXT NOT NULL DEFAULT 'active',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            CONSTRAINT uq_canon_node_ref UNIQUE (project_id, ref_type, ref_id),
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(parent_id) REFERENCES canon_nodes(id) ON DELETE SET NULL
        )
    """,
    "canon_versions": """
        CREATE TABLE canon_versions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            ref_type TEXT NOT NULL,
            ref_id TEXT NOT NULL,
            version_no INTEGER NOT NULL,
            content_json TEXT NOT NULL DEFAULT '{}',
            source_chapter_id TEXT,
            source_job_id TEXT,
            source_agent TEXT NOT NULL DEFAULT 'manual',
            change_reason TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 1.0,
            created_at DATETIME NOT NULL,
            CONSTRAINT uq_canon_version_ref_no UNIQUE (project_id, ref_type, ref_id, version_no),
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(source_chapter_id) REFERENCES chapters(id) ON DELETE SET NULL,
            FOREIGN KEY(source_job_id) REFERENCES generation_jobs(id) ON DELETE SET NULL
        )
    """,
    "canon_change_proposals": """
        CREATE TABLE canon_change_proposals (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT,
            operation TEXT NOT NULL DEFAULT 'create',
            before_json TEXT NOT NULL DEFAULT '{}',
            after_json TEXT NOT NULL DEFAULT '{}',
            source_chapter_id TEXT,
            source_job_id TEXT,
            source_agent TEXT NOT NULL DEFAULT 'agent',
            approval_status TEXT NOT NULL DEFAULT 'pending',
            confidence REAL NOT NULL DEFAULT 0.8,
            reason TEXT NOT NULL DEFAULT '',
            created_at DATETIME NOT NULL,
            decided_at DATETIME,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY(source_chapter_id) REFERENCES chapters(id) ON DELETE SET NULL,
            FOREIGN KEY(source_job_id) REFERENCES generation_jobs(id) ON DELETE SET NULL
        )
    """,
    "canon_classifications": """
        CREATE TABLE canon_classifications (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            ref_type TEXT NOT NULL,
            ref_id TEXT NOT NULL,
            dimension TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at DATETIME NOT NULL,
            CONSTRAINT uq_canon_classification UNIQUE (project_id, ref_type, ref_id, dimension, value),
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
    """,
}


def apply_sqlite_runtime_migrations(engine: Engine) -> None:
    """Small dev-time migration layer for the local SQLite MVP database.

    Alembic remains the formal migration tool, but the project is iterating in
    Codex sessions where an existing local DB may already have old tables. This
    keeps the 1.0 app runnable without asking the user to drop their data.
    """

    if not engine.url.drivername.startswith("sqlite"):
        return

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table_name, ddl in SQLITE_TABLE_DEFAULTS.items():
            if table_name not in existing_tables:
                connection.execute(text(ddl))
        for table_name, columns in SQLITE_COLUMN_DEFAULTS.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, ddl in columns.items():
                if column_name in existing_columns:
                    continue
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
