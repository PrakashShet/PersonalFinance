"""One generic selectable tile for every master list (accounts, holdings,
loans, goals, income sources, projections). Replaces six near-identical tile
classes that each carried their own hardcoded stylesheet."""
from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from ui.theme import icons, theme
from ui.widgets.common import Badge, ElidedLabel, progress, repolish, set_tone


class ListTile(QFrame):
    clicked = pyqtSignal(object)
    activated = pyqtSignal(object)

    def __init__(
        self,
        key: Any,
        title: str,
        subtitle: str = "",
        value: str = "",
        value_tone: Optional[str] = None,
        badge: Optional[tuple[str, str]] = None,
        chip: Optional[tuple[str, str]] = None,
        progress_pct: Optional[float] = None,
        progress_tone: str = "",
        icon_name: Optional[str] = None,
        muted: bool = False,
        selected: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.key = key
        self.setObjectName("tile")
        self.setProperty("selected", selected)
        self.setProperty("muted", muted)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(12)
        self._icon_name = icon_name
        self._icon: Optional[QLabel] = None
        if icon_name:
            self._icon = QLabel()
            self._icon.setObjectName("tileIcon")
            self._icon.setFixedSize(36, 36)
            self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            top.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignVCenter)

        text = QVBoxLayout()
        text.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self.title_label = ElidedLabel(title, "tileTitle")
        title_row.addWidget(self.title_label, 1)
        if badge:
            title_row.addWidget(Badge(badge[0], badge[1]), 0)
        text.addLayout(title_row)
        if subtitle:
            text.addWidget(ElidedLabel(subtitle, "tileMeta"))
        top.addLayout(text, 1)

        right = QVBoxLayout()
        right.setSpacing(4)
        if value:
            self.value_label = QLabel(value)
            self.value_label.setObjectName("tileValue")
            self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if value_tone:
                set_tone(self.value_label, value_tone)
            right.addWidget(self.value_label, 0, Qt.AlignmentFlag.AlignRight)
        if chip:
            right.addWidget(Badge(chip[0], chip[1]), 0, Qt.AlignmentFlag.AlignRight)
        top.addLayout(right, 0)
        root.addLayout(top)

        if progress_pct is not None:
            root.addWidget(progress(progress_pct, progress_tone))

        self._paint_icon()
        theme.changed.connect(self._paint_icon)

    def _paint_icon(self) -> None:
        if self._icon is not None and self._icon_name:
            token = "accent_text" if self.property("selected") else "text_muted"
            self._icon.setPixmap(icons.pixmap(self._icon_name, theme.color(token), 18))

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        repolish(self)
        for child in self.findChildren(QLabel):
            repolish(child)
        self._paint_icon()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.key)
        super().mouseDoubleClickEvent(event)
