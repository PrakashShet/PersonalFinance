"""Idempotent, additive schema migrations.

`schema.sql` uses ``CREATE TABLE IF NOT EXISTS``, so columns added to a table
definition are NOT applied to a database created before the column existed.
This module bridges that gap with ``ALTER TABLE`` on every boot - safe to run
repeatedly. Called from ``main.bootstrap()`` right after the schema is applied.

The account detail columns are derived from ``config.account_fields`` so the
model, the database, and the UI cannot drift apart.
"""
from __future__ import annotations

from config.account_fields import column_additions
from db.connection import Database
from utils.logger import get_logger

log = get_logger(__name__)

SCHEMA_VERSION = 1


def _ensure_version_table(db: Database) -> None:
    db.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "  id INTEGER PRIMARY KEY CHECK (id = 1),"
        "  version INTEGER NOT NULL"
        ")"
    )
    row = db.fetch_one("SELECT version FROM schema_version WHERE id = 1")
    if row is None:
        db.execute(
            "INSERT INTO schema_version (id, version) VALUES (1, 0)"
        )
    db.commit()


def _current_version(db: Database) -> int:
    row = db.fetch_one("SELECT version FROM schema_version WHERE id = 1")
    return int(row["version"]) if row else 0


def _set_version(db: Database, version: int) -> None:
    db.execute(
        "UPDATE schema_version SET version = ? WHERE id = 1", (version,)
    )
    db.commit()


def _additions() -> dict[str, dict[str, str]]:
    # table -> {column_name: column_definition}
    return {
        "accounts": column_additions(),
        # Account links added after these tables shipped. Added as plain
        # INTEGER (FK enforcement comes from schema.sql on fresh databases;
        # ALTER TABLE cannot retrofit the constraint).
        "income_sources": {"deposit_account_id": "INTEGER"},
        "liabilities": {"account_id": "INTEGER"},
    }


def _existing_columns(db: Database, table: str) -> set[str]:
    rows = db.fetch_all(f"PRAGMA table_info({table})")
    return {row["name"] for row in rows}


def run_migrations(db: Database) -> None:
    """Apply all pending additive migrations. Idempotent."""
    _ensure_version_table(db)
    version = _current_version(db)

    for table, columns in _additions().items():
        present = _existing_columns(db, table)
        if not present:
            # Table doesn't exist yet (a fresh DB already has the columns from
            # schema.sql); nothing to migrate.
            continue
        for col, sqltype in columns.items():
            if col not in present:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {sqltype}")
                log.info(f"Migration: added column {table}.{col}")
        db.commit()

    if version < SCHEMA_VERSION:
        _set_version(db, SCHEMA_VERSION)
        log.info(f"Schema version set to {SCHEMA_VERSION}")
