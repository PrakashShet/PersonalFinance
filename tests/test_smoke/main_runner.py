"""Runs the real ``main.main()`` in a child process, for the start-up tests.

The parent sets ``PFM_HOME`` (a throwaway folder) and ``E2E_*`` variables. Message
boxes and toasts are recorded instead of shown, the event loop quits on its own
after ``E2E_QUIT_MS``, and the outcome is written as JSON to ``E2E_OUT``.

    E2E_HOLD_LOCK=1          another copy is "already running"
    E2E_ACTION=add_account   add an account through the service once the window is up
    E2E_ACTION=raise         raise an error inside a handler once the window is up
    E2E_LEGACY=<folder>      pretend this is the old beside-the-exe data folder
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QLockFile, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox  # noqa: E402

record: dict = {"messages": [], "toasts": [], "exit": None}


def _box(kind):
    def show(parent, title, text, *args, **kwargs):
        record["messages"].append([kind, title, text])
        return QMessageBox.StandardButton.Ok
    return staticmethod(show)


for _kind in ("information", "warning", "critical", "question"):
    setattr(QMessageBox, _kind, _box(_kind))
QMessageBox.exec = lambda self: record["messages"].append(["box", self.text(), self.informativeText()]) or 0

_real_exec = QApplication.exec


def _exec_then_quit(*_args):
    QTimer.singleShot(int(os.environ.get("E2E_QUIT_MS", "1500")), QApplication.quit)
    return _real_exec()


QApplication.exec = _exec_then_quit

import main as app_main  # noqa: E402
from config.settings import settings  # noqa: E402

app_main.notify = lambda text: record["toasts"].append(text)

if os.environ.get("E2E_LEGACY"):
    object.__setattr__(settings, "LEGACY_DATA_DIR", Path(os.environ["E2E_LEGACY"]))

held = None
if os.environ.get("E2E_HOLD_LOCK"):
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    held = QLockFile(str(settings.LOCK_PATH))
    assert held.tryLock(0), "could not take the lock for the test"

if os.environ.get("E2E_ACTION") == "add_account":
    from models.account import Account

    _real_create = app_main.AppContext.create

    def _create(*args, **kwargs):
        ctx = _real_create(*args, **kwargs)
        QTimer.singleShot(100, lambda: ctx.account_service.create_account(
            Account(name="Added before the crash", account_type="cash", current_balance=1_234.0)))
        return ctx

    app_main.AppContext.create = staticmethod(_create)

if os.environ.get("E2E_ACTION") == "raise":
    _real_create_r = app_main.AppContext.create

    def _create_r(*args, **kwargs):
        ctx = _real_create_r(*args, **kwargs)
        QTimer.singleShot(100, lambda: 1 / 0)          # a bug inside a handler
        return ctx

    app_main.AppContext.create = staticmethod(_create_r)

try:
    record["exit"] = app_main.main()
finally:
    Path(os.environ["E2E_OUT"]).write_text(json.dumps(record), encoding="utf-8")
