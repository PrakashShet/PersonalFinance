"""UI smoke tests — headless PyQt6 window construction."""
from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QListWidget, QStackedWidget

from config.settings import settings
from db.connection import Database
from db.migrate import run_migrations
from services.data_loader import DataLoader
from tests.conftest import SCHEMA_PATH

pytestmark = pytest.mark.smoke


@pytest.fixture
def isolated_app_db(tmp_path, empty_store):
    """Connect the app singleton to an isolated DB before views are constructed."""
    from db.connection import db

    db.connect(tmp_path / "ui_smoke.db")
    db.apply_schema(SCHEMA_PATH)
    run_migrations(db)
    loader = DataLoader(db)
    loader.load_seed_data(settings.SEED_DIR)
    loader.load_store_data(empty_store)
    yield db
    db.close()


def test_main_window_loads_all_nav_pages(qtbot, isolated_app_db):
    from ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    assert isinstance(window.sidebar, QListWidget)
    assert isinstance(window.stack, QStackedWidget)
    assert window.sidebar.count() == 8
    assert window.stack.count() == 8

    labels = [window.sidebar.item(i).text() for i in range(window.sidebar.count())]
    assert labels[0] == "Dashboard"
    assert "Transactions" in labels
    assert "Accounts" in labels


def test_main_window_nav_switch(qtbot, isolated_app_db):
    from ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    window.sidebar.setCurrentRow(2)  # Transactions
    assert window.stack.currentIndex() == 2

    window.sidebar.setCurrentRow(1)  # Accounts
    assert window.stack.currentIndex() == 1


def test_main_window_nav_switch_all_pages(qtbot, isolated_app_db):
    """Every nav page (incl. Goals, Investments, Liabilities, Projections)
    can be switched to without raising."""
    from ui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    for i in range(window.sidebar.count()):
        window.sidebar.setCurrentRow(i)
        assert window.stack.currentIndex() == i
        assert window.stack.currentWidget() is not None
