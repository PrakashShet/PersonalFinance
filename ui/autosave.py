"""AutoSaver - saves shortly after every change, plus a periodic safety net.

Before 1.0 the app saved only every 60 seconds and on exit; a crash could
lose up to a minute of edits. Now any data change schedules a save
``SAVE_DEBOUNCE_MS`` later (edits in quick succession are batched), and the
periodic timer still runs to record the daily net-worth snapshot and retry
after a failure. Saves write only files that changed, atomically.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from utils.logger import get_logger

log = get_logger(__name__)


class AutoSaver(QObject):
    status = pyqtSignal(str, str)          # state ("saved" | "saving" | "error"), text

    def __init__(self, storage, before_save: Optional[Callable[[], None]],
                 debounce_ms: int = 800, interval_sec: int = 60, parent=None) -> None:
        super().__init__(parent)
        self.storage = storage
        self._before = before_save
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(debounce_ms)
        self._debounce.timeout.connect(self.save_now)
        self._periodic = QTimer(self)
        self._periodic.setInterval(max(15, interval_sec) * 1000)
        self._periodic.timeout.connect(self.save_now)
        self._periodic.start()

    def request(self, *_args) -> None:
        if not self._debounce.isActive():
            self.status.emit("saving", "Saving...")
        self._debounce.start()

    def save_now(self) -> bool:
        self._debounce.stop()
        try:
            self.storage.save(self._before)
        except Exception as e:  # noqa: BLE001 - surfaced to the user, logged with traceback
            log.error(f"Autosave failed: {e}")
            self.status.emit("error", "Couldn't save - will retry")
            QTimer.singleShot(10_000, self.save_now)
            return False
        when = self.storage.last_saved_at.strftime("%I:%M %p").lstrip("0")
        self.status.emit("saved", f"All changes saved · {when}")
        return True

    def stop(self) -> None:
        self._debounce.stop()
        self._periodic.stop()
