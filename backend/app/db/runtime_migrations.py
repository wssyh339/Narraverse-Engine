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
        for table_name, columns in SQLITE_COLUMN_DEFAULTS.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, ddl in columns.items():
                if column_name in existing_columns:
                    continue
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}"))
