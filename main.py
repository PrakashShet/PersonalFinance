"""Personal Finance Manager - entry point.

Startup
  1. One copy at a time: two copies would each save over the other's changes.
  2. Theme first, so even an error message matches the rest of the app.
  3. Open storage (services/storage.py): read and validate every data file,
     migrate the format if needed (after a backup), load, take a startup
     backup. A damaged file stops here with recovery instructions - nothing
     is overwritten.
  4. Main window. Saves follow every change (ui/autosave.py), plus a periodic
     safety net that also records the daily net-worth snapshot.

Shutdown: final save, then a shutdown backup.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QLockFile, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QMessageBox

from config.settings import settings
from db.connection import db
from services.app_context import AppContext
from services.preferences_service import PreferencesService
from services.storage import Storage, StoreLoadError, StoreVersionError
from ui.autosave import AutoSaver
from ui.main_window import MainWindow
from ui.theme import theme
from ui.widgets.toast import notify
from utils.logger import get_logger

log = get_logger(__name__)


def import_legacy_data() -> Optional[Path]:
    """Builds before 1.0 kept data beside the .exe. Copy it to the new home
    once, if the new home has no data yet. The old folder is left untouched."""
    legacy = settings.LEGACY_DATA_DIR
    if legacy is None:
        return None
    src = legacy / "store"
    if not src.is_dir() or not any(src.glob("*.json")):
        return None
    if settings.STORE_DIR.is_dir() and any(settings.STORE_DIR.glob("*.json")):
        return None
    shutil.copytree(src, settings.STORE_DIR, dirs_exist_ok=True)
    old_backups = legacy / "user" / "backups"
    if old_backups.is_dir():
        shutil.copytree(old_backups, settings.BACKUP_DIR, dirs_exist_ok=True)
    log.info(f"Imported data from the old location {legacy}")
    return legacy


def remove_legacy_sqlite() -> None:
    """SQLite now lives in memory; an old app.db file is stale scratch."""
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(settings.LEGACY_SQLITE_PATH) + suffix)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def show_store_error(err: StoreLoadError, latest_backup: Optional[Path]) -> None:
    box = QMessageBox(QMessageBox.Icon.Critical, settings.APP_NAME,
                      f"Your data file “{err.path.name}” {err.reason}")
    lines = [
        "The app has stopped before changing anything, so nothing has been overwritten.",
        "",
        "To recover: copy the files from the newest backup folder into your data folder "
        "(replace when asked), then start the app again.",
        "",
        f"Data folder:  {settings.STORE_DIR}",
        f"Newest backup:  {latest_backup or 'none found'}",
    ]
    box.setInformativeText("\n".join(lines))
    open_backup = box.addButton("Open backup folder", QMessageBox.ButtonRole.ActionRole) if latest_backup else None
    open_data = box.addButton("Open data folder", QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Close)
    box.exec()
    clicked = box.clickedButton()
    if clicked is open_backup and latest_backup:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(latest_backup)))
    elif clicked is open_data:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(settings.STORE_DIR)))


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(settings.APP_NAME)
    app.setApplicationVersion(settings.APP_VERSION)
    app.setOrganizationName("PersonalFinanceManager")
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

    prefs = PreferencesService(settings.PREFS_PATH)
    theme.install(app, prefs.get("theme") or "system")

    lock = QLockFile(str(settings.LOCK_PATH))
    lock.setStaleLockTime(0)          # held for the whole session; crashes are detected by PID
    if not lock.tryLock(200):
        QMessageBox.information(
            None, settings.APP_NAME,
            "Personal Finance Manager is already open.\n\nUse the window that's already "
            "running - two copies at once would overwrite each other's changes.")
        return 0

    log.info(f"Starting {settings.APP_NAME} {settings.APP_VERSION} (data: {settings.DATA_DIR})")
    imported = import_legacy_data()
    remove_legacy_sqlite()

    db.connect(settings.SQLITE_PATH)
    storage = Storage(
        db, settings.STORE_DIR, settings.BACKUP_DIR, settings.SEED_DIR,
        settings.REFERENCE_DIR, settings.SCHEMA_PATH, app_version=settings.APP_VERSION,
        mirror_dir=lambda: prefs.get("backup_mirror_dir"),
    )
    try:
        report = storage.open()
    except StoreLoadError as e:
        log.error(f"Store failed validation: {e}")
        show_store_error(e, storage.latest_backup())
        return 1
    except StoreVersionError as e:
        log.error(str(e))
        QMessageBox.critical(None, settings.APP_NAME, str(e))
        return 1
    except Exception as e:  # e.g. a backup could not be written before an upgrade
        log.exception("Opening the data store failed")
        QMessageBox.critical(
            None, settings.APP_NAME,
            f"Your data couldn't be opened safely, so the app stopped before changing "
            f"anything.\n\n{e}\n\nData folder: {settings.STORE_DIR}\nLog: {settings.LOG_FILE}")
        return 1

    ctx = AppContext.create(db, preferences=prefs, storage=storage)

    def snapshot() -> None:
        try:
            ctx.net_worth_service.take_snapshot()
        except Exception:  # never let a snapshot stop a save
            log.exception("Net-worth snapshot failed")

    window = MainWindow(ctx)
    saver = AutoSaver(storage, snapshot, settings.SAVE_DEBOUNCE_MS, settings.AUTOSAVE_INTERVAL_SEC)
    saver.status.connect(window.set_save_status)
    ctx.events.changed.connect(saver.request)
    window.show()
    saver.save_now()

    if report.migrated_from is not None:
        notify("Your data was upgraded to the new format - a backup was kept")
    elif imported is not None:
        notify("Your data was moved to its new home in AppData")

    def shutdown() -> None:
        saver.stop()
        try:
            storage.close(snapshot)
        except Exception:
            log.exception("Final save failed - your data is as of the last successful save")
        db.close()
        lock.unlock()
        log.info("Shutdown complete.")

    app.aboutToQuit.connect(shutdown)
    app.commitDataRequest.connect(lambda _manager: saver.save_now())
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
