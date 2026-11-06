"""Tile widget representing a single income source in the Income view.

Presentational only: the view computes display strings and passes them in.
Single click selects the tile (updates the detail pane); double click opens
the edit dialog. Selection highlight is toggled via ``set_selected``.

Styled to match the app's dark, warm-tan theme (see theme.qss → accountTile).
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from models.income import IncomeSource

# Frame styling matches QFrame#accountTile in theme.qss (dark, warm-tan).
_STYLE = """
QFrame#incomeTile {
    background-color: rgba(201, 170, 122, 0.10);
    border: 1px solid rgba(201, 170, 122, 0.30);
    border-radius: 14px;
}
QFrame#incomeTile:hover {
    background-color: rgba(201, 170, 122, 0.17);
    border-color: rgba(201, 170, 122, 0.55);
}
QFrame#incomeTile[selected="true"] {
    background-color: rgba(201, 170, 122, 0.22);
    border: 2px solid rgba(201, 170, 122, 0.78);
}
QFrame#incomeTile[inactive="true"] {
    background-color: rgba(201, 170, 122, 0.05);
    border-color: rgba(201, 170, 122, 0.18);
}
"""

# (background, foreground) chips that read well on the dark theme
_ACTIVE_BADGE   = ("rgba(16, 185, 129, 0.16)", "#6ee7b7")
_INACTIVE_BADGE = ("rgba(201, 170, 122, 0.10)", "#9c8869")
_STATUS = {
    "logged":  ("Logged this month",  "rgba(16, 185, 129, 0.16)", "#6ee7b7"),
    "pending": ("Pending this month", "rgba(245, 158, 11, 0.16)", "#fbbf24"),
}


def _badge(text: str, bg: str, fg: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background-color:{bg}; color:{fg}; border-radius:6px; "
        f"padding:2px 8px; font-size:11px; font-weight:600;"
    )
    return lbl


class IncomeSourceTile(QFrame):
    def __init__(
        self,
        source: IncomeSource,
        *,
        type_label: str,
        type_bg: str,
        type_fg: str,
        freq_label: str,
        account_name: Optional[str],
        net_text: str,
        month_status: str,                       # "logged" | "pending" | "na"
        selected: bool,
        on_click: Callable[[IncomeSource], None],
        on_activate: Callable[[IncomeSource], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.source = source
        self._on_click = on_click
        self._on_activate = on_activate

        self.setObjectName("incomeTile")
        self.setProperty("selected", selected)
        self.setProperty("inactive", source.is_active != 1)
        self.setStyleSheet(_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(108)

        self._build(type_label, type_bg, type_fg, freq_label, account_name, net_text, month_status)

    def _build(self, type_label, type_bg, type_fg, freq_label, account_name, net_text, status) -> None:
        s = self.source
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        # Header: name + active/inactive badge
        header = QHBoxLayout()
        name = QLabel(s.name or "Unnamed")
        name.setWordWrap(True)
        name.setStyleSheet("color:#f4eee2; font-size:16px; font-weight:700; background:transparent;")
        header.addWidget(name, 1)
        ab_bg, ab_fg = _ACTIVE_BADGE if s.is_active else _INACTIVE_BADGE
        header.addWidget(_badge("Active" if s.is_active else "Inactive", ab_bg, ab_fg), 0)
        root.addLayout(header)

        # Meta: type badge + frequency + deposit account
        meta = QHBoxLayout()
        meta.setSpacing(8)
        meta.addWidget(_badge(type_label, type_bg, type_fg), 0)
        if account_name:
            meta_lbl = QLabel(f"{freq_label}   ·   → {account_name}")
            meta_lbl.setStyleSheet("color:#c4a878; font-size:12px; background:transparent;")
        else:
            meta_lbl = QLabel(f"{freq_label}   ·   → Not linked")
            meta_lbl.setStyleSheet("color:#9c8869; font-size:12px; background:transparent;")
        meta.addWidget(meta_lbl, 1)
        root.addLayout(meta)

        # Bottom: net / month  +  this-month status chip
        bottom = QHBoxLayout()
        net = QLabel(f"Net / mo:  {net_text}")
        net.setStyleSheet("color:#f4eee2; font-size:15px; font-weight:700; background:transparent;")
        bottom.addWidget(net, 1)
        if status in _STATUS:
            text, bg, fg = _STATUS[status]
            bottom.addWidget(_badge(text, bg, fg), 0)
        root.addLayout(bottom)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        # Re-apply the property selector.
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click(self.source)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_activate(self.source)
        super().mouseDoubleClickEvent(event)
