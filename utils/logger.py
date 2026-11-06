"""Centralized logger. Writes to ``settings.LOG_FILE`` (rotating) and stdout.

The log location comes from ``config.settings`` so a packaged build logs to
``%APPDATA%\\PersonalFinanceManager\\logs`` instead of PyInstaller's temporary
extraction folder, and tests (``PFM_HOME`` set) never write to the real log.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from config.settings import settings

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"

_configured = False


def _configure() -> None:
    global _configured
    if _configured:
        return
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # A windowed .exe has no console: sys.stdout is None there.
    if sys.stdout is not None:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(stream)

    try:
        settings.LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_h = RotatingFileHandler(
            settings.LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8"
        )
        file_h.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(file_h)
    except OSError:
        # Logging must never stop the app from starting.
        pass

    _configured = True


def get_logger(name: str) -> logging.Logger:
    _configure()
    return logging.getLogger(name)
