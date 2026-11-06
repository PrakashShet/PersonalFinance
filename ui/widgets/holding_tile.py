"""Tile widget representing a single investment holding in the Investments view.

Presentational only: the view computes display strings and passes them in.
Single click selects the tile (shows the detail panel); double click opens the
edit dialog. Selection highlight is toggled via ``set_selected``.

Styled to match the app's dark, warm-tan theme (see IncomeSourceTile).
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from models.holding import Holding

_STYLE = """
QFrame#holdingTile {
    background-color: rgba(201, 170, 122, 0.10);
    border: 1px solid rgba(201, 170, 122, 0.30);
    border-radius: 14px;
}
QFrame#holdingTile:hover {
    background-color: rgba(201, 170, 122, 0.17);
    border-color: rgba(201, 170, 122, 0.55);
}
QFrame#holdingTile[selected="true"] {
    background-color: rgba(201, 170, 122, 0.22);
    border: 2px solid rgba(201, 170, 122, 0.78);
}
QFrame#holdingTile[inactive="true"] {
    background-color: rgba(201, 170, 122, 0.05);
    border-color: rgba(201, 170, 122, 0.18);
}
"""

_ACTIVE_BADGE   = ("rgba(16, 185, 129, 0.16)", "#6ee7b7")
_INACTIVE_BADGE = ("rgba(201, 170, 122, 0.10)", "#9c8869")
# P&L chips
_GAIN = ("rgba(16, 185, 129, 0.16)", "#6ee7b7")
_LOSS = ("rgba(239, 68, 68, 0.16)", "#fca5a5")


def _badge(text: str, bg: str, fg: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background-color:{bg}; color:{fg}; border-radius:6px; "
        f"padding:2px 8px; font-size:11px; font-weight:600;"
    )
    return lbl


class HoldingTile(QFrame):
    def __init__(
        self,
        holding: Holding,
        *,
        type_label: str,
        type_bg: str,
        type_fg: str,
        institution: Optional[str],
        value_text: str,
        return_text: str,
        positive: bool,
        selected: bool,
        on_click: Callable[[Holding], None],
        on_activate: Callable[[Holding], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.holding = holding
        self._on_click = on_click
        self._on_activate = on_activate

        self.setObjectName("holdingTile")
        self.setProperty("selected", selected)
        self.setProperty("inactive", holding.is_active != 1)
        self.setStyleSheet(_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(108)

        self._build(type_label, type_bg, type_fg, institution, value_text, return_text, positive)

    def _build(self, type_label, type_bg, type_fg, institution, value_text, return_text, positive) -> None:
        h = self.holding
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        # Header: name + active/inactive badge
        header = QHBoxLayout()
        name = QLabel(h.name or "Unnamed")
        name.setWordWrap(True)
        name.setStyleSheet("color:#f4eee2; font-size:16px; font-weight:700; background:transparent;")
        header.addWidget(name, 1)
        ab_bg, ab_fg = _ACTIVE_BADGE if h.is_active else _INACTIVE_BADGE
        header.addWidget(_badge("Active" if h.is_active else "Inactive", ab_bg, ab_fg), 0)
        root.addLayout(header)

        # Meta: type badge + institution
        meta = QHBoxLayout()
        meta.setSpacing(8)
        meta.addWidget(_badge(type_label, type_bg, type_fg), 0)
        if institution:
            inst_lbl = QLabel(institution)
            inst_lbl.setStyleSheet("color:#c4a878; font-size:12px; background:transparent;")
        else:
            inst_lbl = QLabel("—")
            inst_lbl.setStyleSheet("color:#9c8869; font-size:12px; background:transparent;")
        meta.addWidget(inst_lbl, 1)
        root.addLayout(meta)

        # Bottom: current value + return chip
        bottom = QHBoxLayout()
        value = QLabel(f"Value:  {value_text}")
        value.setStyleSheet("color:#f4eee2; font-size:15px; font-weight:700; background:transparent;")
        bottom.addWidget(value, 1)
        bg, fg = _GAIN if positive else _LOSS
        bottom.addWidget(_badge(return_text, bg, fg), 0)
        root.addLayout(bottom)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click(self.holding)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_activate(self.holding)
        super().mouseDoubleClickEvent(event)
