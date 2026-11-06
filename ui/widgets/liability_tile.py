"""Tile widget representing a single liability in the Liabilities view.

Presentational only: the view computes display strings and passes them in.
Single click selects the tile (shows the detail panel); double click opens the
edit dialog. Selection highlight is toggled via ``set_selected``.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from models.liability import Liability

_STYLE = """
QFrame#liabilityTile {
    background-color: rgba(201, 170, 122, 0.10);
    border: 1px solid rgba(201, 170, 122, 0.30);
    border-radius: 14px;
}
QFrame#liabilityTile:hover {
    background-color: rgba(201, 170, 122, 0.17);
    border-color: rgba(201, 170, 122, 0.55);
}
QFrame#liabilityTile[selected="true"] {
    background-color: rgba(201, 170, 122, 0.22);
    border: 2px solid rgba(201, 170, 122, 0.78);
}
QFrame#liabilityTile[inactive="true"] {
    background-color: rgba(201, 170, 122, 0.05);
    border-color: rgba(201, 170, 122, 0.18);
}
"""

_ACTIVE_BADGE   = ("rgba(16, 185, 129, 0.16)", "#6ee7b7")
_INACTIVE_BADGE = ("rgba(201, 170, 122, 0.10)", "#9c8869")
_DANGER_CHIP    = ("rgba(239, 68, 68, 0.16)", "#fca5a5")
_NEUTRAL_CHIP   = ("rgba(201, 170, 122, 0.16)", "#d2b98f")


def _badge(text: str, bg: str, fg: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background-color:{bg}; color:{fg}; border-radius:6px; "
        f"padding:2px 8px; font-size:11px; font-weight:600;"
    )
    return lbl


class LiabilityTile(QFrame):
    def __init__(
        self,
        liability: Liability,
        *,
        type_label: str,
        type_bg: str,
        type_fg: str,
        lender: Optional[str],
        outstanding_text: str,
        chip_text: str,
        chip_danger: bool,
        selected: bool,
        on_click: Callable[[Liability], None],
        on_activate: Callable[[Liability], None],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.liability = liability
        self._on_click = on_click
        self._on_activate = on_activate

        self.setObjectName("liabilityTile")
        self.setProperty("selected", selected)
        self.setProperty("inactive", liability.is_active != 1)
        self.setStyleSheet(_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(108)

        self._build(type_label, type_bg, type_fg, lender, outstanding_text, chip_text, chip_danger)

    def _build(self, type_label, type_bg, type_fg, lender, outstanding_text, chip_text, chip_danger) -> None:
        lb = self.liability
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        header = QHBoxLayout()
        name = QLabel(lb.name or "Unnamed")
        name.setWordWrap(True)
        name.setStyleSheet("color:#f4eee2; font-size:16px; font-weight:700; background:transparent;")
        header.addWidget(name, 1)
        ab_bg, ab_fg = _ACTIVE_BADGE if lb.is_active else _INACTIVE_BADGE
        header.addWidget(_badge("Active" if lb.is_active else "Inactive", ab_bg, ab_fg), 0)
        root.addLayout(header)

        meta = QHBoxLayout()
        meta.setSpacing(8)
        meta.addWidget(_badge(type_label, type_bg, type_fg), 0)
        if lender:
            lender_lbl = QLabel(lender)
            lender_lbl.setStyleSheet("color:#c4a878; font-size:12px; background:transparent;")
        else:
            lender_lbl = QLabel("—")
            lender_lbl.setStyleSheet("color:#9c8869; font-size:12px; background:transparent;")
        meta.addWidget(lender_lbl, 1)
        root.addLayout(meta)

        bottom = QHBoxLayout()
        out = QLabel(f"Outstanding:  {outstanding_text}")
        out.setStyleSheet("color:#fca5a5; font-size:15px; font-weight:700; background:transparent;")
        bottom.addWidget(out, 1)
        if chip_text:
            bg, fg = _DANGER_CHIP if chip_danger else _NEUTRAL_CHIP
            bottom.addWidget(_badge(chip_text, bg, fg), 0)
        root.addLayout(bottom)

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_click(self.liability)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._on_activate(self.liability)
        super().mouseDoubleClickEvent(event)
