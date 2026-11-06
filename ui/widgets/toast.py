"""Small confirmation toast shown at the bottom of the window."""
from __future__ import annotations

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QLabel, QWidget


class Toast(QLabel):
    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self.setObjectName("toast")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, ms: int = 2600) -> None:
        self.setText(text)
        self.adjustSize()
        host = self.parentWidget()
        if host is not None:
            x = (host.width() - self.width()) // 2
            y = host.height() - self.height() - 28
            self.move(max(12, x), max(12, y))
        self.raise_()
        self.show()
        self._timer.start(ms)


_notifier = None


def register(fn) -> None:
    """MainWindow registers its toast; views call :func:`notify`."""
    global _notifier
    _notifier = fn


def notify(text: str) -> None:
    if _notifier is not None:
        _notifier(text)
