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


@pytest.fixture(autouse=True)
def _destroy_windows_after_each_test():
    """Destroy every window a test leaves behind.

    A closed window still exists and still reacts to the theme and data signals
    of the shared singletons - after its test's database is closed. Deleting it
    disconnects it, so no test can disturb the next one.
    """
    yield
    from PyQt6.QtCore import QEvent
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for widget in app.topLevelWidgets():
        widget.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)


@pytest.fixture
def isolated_app_db(tmp_path: Path, empty_store: Path):
    """Connect the app's shared ``db`` to an isolated database while a UI test runs.

    Windows created by earlier tests stay alive and still react to theme changes;
    with the shared connection open they refresh harmlessly instead of failing.
    """
    from db.connection import db

    db.connect(tmp_path / "ui_smoke.db")
    db.apply_schema(SCHEMA_PATH)
    run_migrations(db)
    loader = DataLoader(db)
    loader.load_seed_data(settings.SEED_DIR)
    loader.load_store_data(empty_store)
    yield db
    db.close()


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
