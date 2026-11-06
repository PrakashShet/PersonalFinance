"""Shared pytest fixtures for Personal Finance Manager."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Point the app's home (data, backups, preferences, logs) at a throwaway folder
# BEFORE anything imports config.settings, so no test can touch real data.
os.environ["PFM_HOME"] = tempfile.mkdtemp(prefix="pfm-test-home-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from config.settings import settings  # noqa: E402
from db.connection import Database
from db.migrate import run_migrations
from services.data_loader import STORE_LOAD_ORDER, DataLoader

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = PROJECT_ROOT / "db" / "schema.sql"


@pytest.fixture
def temp_db(tmp_path: Path) -> Database:
    """Empty SQLite database with schema and additive migrations applied."""
    database = Database()
    database.connect(tmp_path / "test.db")
    database.apply_schema(SCHEMA_PATH)
    run_migrations(database)
    yield database
    database.close()


@pytest.fixture
def empty_store(tmp_path: Path) -> Path:
    """Writable store directory with empty JSON files for every table."""
    store = tmp_path / "store"
    store.mkdir()
    for filename, _ in STORE_LOAD_ORDER:
        (store / filename).write_text("[]", encoding="utf-8")
    return store


@pytest.fixture
def bootstrapped_session(tmp_path: Path, empty_store: Path):
    """Isolated DB hydrated from seed + empty store (mirrors app bootstrap)."""
    database = Database()
    database.connect(tmp_path / "session.db")
    database.apply_schema(SCHEMA_PATH)
    run_migrations(database)

    loader = DataLoader(database)
    loader.load_seed_data(settings.SEED_DIR)
    loader.load_store_data(empty_store)

    ref_dir = tmp_path / "reference"
    ref_dir.mkdir()
    loader.load_reference_data(ref_dir)

    yield database, empty_store
    database.close()
