"""Centralized application settings and paths.

Where things live
-----------------
``APP_HOME`` is the one folder that holds everything the user owns::

    APP_HOME/data/store/                the user's records (JSON, source of truth)
    APP_HOME/data/user/backups/         automatic backups (tiered retention)
    APP_HOME/data/user/preferences.json theme, projection assumptions, ...
    APP_HOME/logs/app.log

``APP_HOME`` is resolved in this order:

1. the ``PFM_HOME`` environment variable (tests, portable installs, power users)
2. the packaged ``.exe``: ``%APPDATA%\\PersonalFinanceManager``. Deliberately
   *not* next to the ``.exe`` - rebuilding with PyInstaller replaces that whole
   folder, which used to put the data (and its backups) in the blast radius.
3. running from source: the project folder (``data/`` and ``logs/`` beside
   ``main.py``), exactly as before.

Read-only assets that ship with the app (seed data, schema, stylesheet) always
come from ``BUNDLE_ROOT``.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

APP_FOLDER_NAME = "PersonalFinanceManager"


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _source_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _bundle_root() -> Path:
    """Read-only bundled assets (PyInstaller's _MEIPASS when frozen)."""
    if _is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return _source_root()


def _app_home() -> Path:
    override = os.environ.get("PFM_HOME", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if _is_frozen():
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_FOLDER_NAME
    return _source_root()


def _legacy_exe_data_dir() -> Optional[Path]:
    """Where builds before 1.0 kept their data: beside the .exe."""
    if _is_frozen():
        return Path(sys.executable).resolve().parent / "data"
    return None


PROJECT_ROOT = _source_root()
BUNDLE_ROOT = _bundle_root()
APP_HOME = _app_home()


@dataclass(frozen=True)
class Settings:
    APP_NAME: str = "Personal Finance Manager"
    APP_VERSION: str = "1.1.0"

    # ---- user-owned, writable ------------------------------------------
    APP_HOME: Path = APP_HOME
    DATA_DIR: Path = APP_HOME / "data"
    STORE_DIR: Path = APP_HOME / "data" / "store"          # source of truth
    CACHE_DIR: Path = APP_HOME / "data" / "cache"
    USER_DIR: Path = APP_HOME / "data" / "user"
    BACKUP_DIR: Path = APP_HOME / "data" / "user" / "backups"
    PREFS_PATH: Path = APP_HOME / "data" / "user" / "preferences.json"
    LOCK_PATH: Path = APP_HOME / "data" / "app.lock"
    LEGACY_DATA_DIR: Optional[Path] = _legacy_exe_data_dir()

    # ---- shipped with the app, read-only --------------------------------
    SEED_DIR: Path = BUNDLE_ROOT / "data" / "seed"
    REFERENCE_DIR: Path = BUNDLE_ROOT / "data" / "reference"
    SCHEMA_PATH: Path = BUNDLE_ROOT / "db" / "schema.sql"
    STYLESHEET_PATH: Path = BUNDLE_ROOT / "ui" / "resources" / "styles" / "theme.qss"

    # SQLite is scratch: rebuilt in memory from the JSON store on every launch,
    # so a schema change never needs an SQLite migration. Older versions kept a
    # file here; it is deleted at startup when found.
    SQLITE_PATH: str = ":memory:"
    LEGACY_SQLITE_PATH: Path = APP_HOME / "data" / "app.db"

    # ---- logging -------------------------------------------------------
    LOG_DIR: Path = APP_HOME / "logs"
    LOG_FILE: Path = APP_HOME / "logs" / "app.log"

    # ---- behaviour -----------------------------------------------------
    DEFAULT_CURRENCY: str = "INR"
    DEFAULT_LOCALE: str = "en_IN"
    SAVE_DEBOUNCE_MS: int = 800        # save this long after the last change
    AUTOSAVE_INTERVAL_SEC: int = 60    # periodic safety net + daily snapshot

    def load_stylesheet(self) -> str:
        """Raw stylesheet template (``ui.theme`` fills in the colour tokens)."""
        try:
            return self.STYLESHEET_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""


settings = Settings()
