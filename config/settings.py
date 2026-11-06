"""Centralized application settings and paths."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path


def _writable_root() -> Path:
    """User-writable directory (project root in dev, folder containing .exe when frozen)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _bundle_root() -> Path:
    """Read-only bundled assets (same as writable root in dev; PyInstaller _MEIPASS when frozen)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", _writable_root()))
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _writable_root()
BUNDLE_ROOT = _bundle_root()


@dataclass(frozen=True)
class Settings:
    APP_NAME: str = "Personal Finance Manager"
    APP_VERSION: str = "0.1.0"

    # Directory layout (writable paths live next to the .exe when frozen)
    DATA_DIR: Path = PROJECT_ROOT / "data"
    SEED_DIR: Path = BUNDLE_ROOT / "data" / "seed"        # ships with the app (read-only)
    STORE_DIR: Path = PROJECT_ROOT / "data" / "store"      # user's persisted data
    CACHE_DIR: Path = PROJECT_ROOT / "data" / "cache"      # NAVs, prices
    REFERENCE_DIR: Path = BUNDLE_ROOT / "data" / "reference"
    BACKUP_DIR: Path = PROJECT_ROOT / "data" / "user" / "backups"

    # Database
    SQLITE_PATH: Path = PROJECT_ROOT / "data" / "app.db"
    SCHEMA_PATH: Path = BUNDLE_ROOT / "db" / "schema.sql"

    # UI
    STYLESHEET_PATH: Path = BUNDLE_ROOT / "ui" / "resources" / "styles" / "theme.qss"
    ICONS_DIR: Path = BUNDLE_ROOT / "ui" / "resources" / "icons"

    # Logging
    LOG_DIR: Path = PROJECT_ROOT / "logs"
    LOG_FILE: Path = PROJECT_ROOT / "logs" / "app.log"

    # Behavior
    DEFAULT_CURRENCY: str = "INR"
    DEFAULT_LOCALE: str = "en_IN"
    AUTOSAVE_INTERVAL_SEC: int = 60  # also persist every minute, not just on exit

    def load_stylesheet(self) -> str:
        try:
            return self.STYLESHEET_PATH.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""


settings = Settings()
