"""Generic projection tile used by the Projections view.

Presentational: the view computes title/subtitle/value/status and passes them
in. Single click selects the tile and updates the right-hand detail pane.
Matches the dark, warm-tan tile look used elsewhere in the app.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

_STYLE = """
QFrame#projectionTile {
    background-color: rgba(201, 170, 122, 0.10);
    border: 1px solid rgba(201, 170, 122, 0.30);
    border-radius: 14px;
}
QFrame#projectionTile:hover {
    background-color: rgba(201, 170, 122, 0.17);
    border-color: rgba(201, 170, 122, 0.55);
}
QFrame#projectionTile[selected="true"] {
    background-color: rgba(201, 170, 122, 0.22);
    border: 2px solid rgba(201, 170, 122, 0.78);
}
"""

# (background, foreground)
_OK    = ("rgba(16, 185, 129, 0.16)", "#6ee7b7")
_WARN  = ("rgba(245, 158, 11, 0.16)", "#fbbf24")
_BAD   = ("rgba(239, 68, 68, 0.16)",  "#fca5a5")
_INFO  = ("rgba(59, 130, 246, 0.16)", "#93c5fd")
_NEUT  = ("rgba(201, 170, 122, 0.18)", "#d2b98f")

_STATUS_PALETTES = {"ok": _OK, "warn": _WARN, "bad": _BAD, "info": _INFO, "neutral": _NEUT}


def _badge(text: str, bg: str, fg: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background-color:{bg}; color:{fg}; border-radius:6px; "
        f"padding:2px 8px; font-size:11px; font-weight:600;"
    )
    return lbl


class ProjectionTile(QFrame):
    def __init__(
        self,
        key: str,                          # opaque identifier returned via on_click
        *,
        title: str,
        subtitle: str = "",
        value_text: str = "",
        status_text: str = "",
        status_kind: str = "neutral",      # ok | warn | bad | info | neutral
        selected: bool = False,
        on_click: Optional[Callable[[str], None]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.key = key
        self._on_click = on_click

        self.setObjectName("projectionTile")
        self.setProperty("selected", selected)
        self.setStyleSheet(_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(104)

        self._build(title, subtitle, value_text, status_text, status_kind)

    def _build(self, title, subtitle, value_text, status_text, status_kind) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        name = QLabel(title)
        name.setStyleSheet("color:#f4eee2; font-size:16px; font-weight:700; background:transparent;")
        name.setWordWrap(True)
        header.addWidget(name, 1)
        if status_text:
            bg, fg = _STATUS_PALETTES.get(status_kind, _NEUT)
            header.addWidget(_badge(status_text, bg, fg), 0)
        root.addLayout(header)

        if subtitle:
            sub = QLabel(subtitle)
            sub.setStyleSheet("color:#c4a878; font-size:12px; background:transparent;")
            sub.setWordWrap(True)
            root.addWidget(sub)

        if value_text:
            val = QLabel(value_text)
            val.setStyleSheet("color:#f4eee2; font-size:15px; font-weight:700; background:transparent;")
            root.addWidget(val)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._on_click:
            self._on_click(self.key)
        super().mousePressEvent(event)
