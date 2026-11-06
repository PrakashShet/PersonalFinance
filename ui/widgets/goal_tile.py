"""Tile widget representing a single goal in the Goals view.

Presentational only: the view computes display strings/colours and passes them
in. Single click selects the tile (shows the detail panel); double click opens
the edit dialog. Selection highlight is toggled via ``set_selected``.
"""
from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout

from models.goal import Goal

_STYLE = """
QFrame#goalTile {
    background-color: rgba(201, 170, 122, 0.10);
    border: 1px solid rgba(201, 170, 122, 0.30);
    border-radius: 14px;
}
QFrame#goalTile:hover {
    background-color: rgba(201, 170, 122, 0.17);
    border-color: rgba(201, 170, 122, 0.55);
}
QFrame#goalTile[selected="true"] {
    background-color: rgba(201, 170, 122, 0.22);
    border: 2px solid rgba(201, 170, 122, 0.78);
}
"""


def _badge(text: str, bg: str, fg: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background-color:{bg}; color:{fg}; border-radius:6px; "
        f"padding:2px 8px; font-size:11px; font-weight:600;"
    )
    return lbl


class GoalTile(QFrame):
    def __init__(
        self,
        goal: Goal,
        *,
        status_label: str,
        status_bg: str,
        status_fg: str,
        priority_label: str,
        priority_bg: str,
        priority_fg: str,
        saved_text: str,
        target_text: str,
        pct: int,
        bar_colour: str,
        selected: bool,
        on_click: Callable[[Goal], None],
        on_activate: Callable[[Goal], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.goal = goal
        self._on_click = on_click
        self._on_activate = on_activate

        self.setObjectName("goalTile")
        self.setProperty("selected", selected)
        self.setStyleSheet(_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(120)

        self._build(status_label, status_bg, status_fg, priority_label,
                    priority_bg, priority_fg, saved_text, target_text, pct, bar_colour)

    def _build(self, status_label, status_bg, status_fg, priority_label,
               priority_bg, priority_fg, saved_text, target_text, pct, bar_colour) -> None:
        g = self.goal
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        # Header: name + status badge
        header = QHBoxLayout()
        name = QLabel(g.name or "Unnamed")
        name.setWordWrap(True)
        name.setStyleSheet("color:#f4eee2; font-size:16px; font-weight:700; background:transparent;")
        header.addWidget(name, 1)
        header.addWidget(_badge(status_label, status_bg, status_fg), 0)
        root.addLayout(header)

        # Meta: priority badge + saved / target
        meta = QHBoxLayout()
        meta.setSpacing(8)
        meta.addWidget(_badge(priority_label, priority_bg, priority_fg), 0)
        amt = QLabel(f"{saved_text}  of  {target_text}")
        amt.setStyleSheet("color:#c4a878; font-size:12px; background:transparent;")
        meta.addWidget(amt, 1)
        root.addLayout(meta)

        # Progress bar
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(max(0, min(100, pct)))
        bar.setTextVisible(True)
        bar.setFormat("%p%  saved")
        bar.setFixedHeight(18)
        bar.setStyleSheet(
            "QProgressBar { background-color: rgba(201,170,122,0.12); border:none; "
            "border-radius:5px; color:#e7e0d4; font-size:10px; }"
            f"QProgressBar::chunk {{ background-color: {bar_colour}; border-radius:5px; }}"
        )
        root.addWidget(bar)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click(self.goal)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_activate(self.goal)
        super().mouseDoubleClickEvent(event)
