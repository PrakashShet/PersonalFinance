"""Personal Finance Manager - Entry Point.

Bootstraps the application: loads CSV/JSON data into SQLite,
launches the PyQt6 main window, and persists changes back on exit.
"""
from __future__ import annotations

import sys
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from config.settings import settings
from db.connection import db
from db.migrate import run_migrations
from services.app_context import AppContext
from services.data_loader import DataLoader
from services.data_persister import DataPersister
from ui.main_window import MainWindow
from utils.logger import get_logger

log = get_logger(__name__)


def _record_net_worth_snapshot() -> None:
    """Persist today's net-worth snapshot (idempotent per day).

    Snapshots accumulate one row per day the app is used, which is what feeds
    the long-term (25-30 year) net-worth trend chart.
    """
    try:
        AppContext.create(db).net_worth_service.take_snapshot()
    except Exception as e:  # never let a snapshot failure crash autosave/quit
        log.error(f"Net-worth snapshot failed: {e}")


def autosave() -> None:
    """Periodic save so a crash can't lose more than one interval of work.

    Skips the per-save backup (backups are made on quit) to stay lightweight.
    """
    try:
        _record_net_worth_snapshot()
        DataPersister(db).dump_store_data(settings.STORE_DIR, make_backup=False)
        log.info("Autosave complete.")
    except Exception as e:
        log.error(f"Autosave failed: {e}")


def bootstrap() -> None:
    """Initialize DB schema and hydrate from CSV/JSON files in data/store."""
    log.info("Bootstrapping application...")
    db.connect(settings.SQLITE_PATH)
    db.apply_schema(settings.SCHEMA_PATH)
    run_migrations(db)                              # additive column upgrades

    loader = DataLoader(db)
    loader.load_seed_data(settings.SEED_DIR)        # categories, account types, etc.
    loader.load_store_data(settings.STORE_DIR)      # user's actual records
    loader.load_reference_data(settings.REFERENCE_DIR)  # tax slabs, inflation, etc.
    log.info("Bootstrap complete.")


def shutdown() -> None:
    """Persist SQLite state back to CSV/JSON files in data/store."""
    log.info("Shutting down - persisting data to disk...")
    _record_net_worth_snapshot()
    persister = DataPersister(db)
    persister.dump_store_data(settings.STORE_DIR)
    db.close()
    log.info("Shutdown complete.")


def main() -> int:
    bootstrap()

    app = QApplication(sys.argv)
    app.setApplicationName(settings.APP_NAME)
    app.setStyleSheet(settings.load_stylesheet())

    window = MainWindow()
    window.show()

    # Periodic autosave so an unexpected exit can't lose a whole session.
    autosave_timer = QTimer()
    autosave_timer.setInterval(max(15, settings.AUTOSAVE_INTERVAL_SEC) * 1000)
    autosave_timer.timeout.connect(autosave)
    autosave_timer.start()
    window._autosave_timer = autosave_timer  # keep a reference alive

    # Persist on quit
    app.aboutToQuit.connect(shutdown)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
