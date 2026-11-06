"""KPI card: label, value, optional hint (e.g. a change vs last month)."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout

from ui.theme import icons, theme
from ui.widgets.common import set_tone


class KpiCard(QFrame):
    def __init__(self, title: str, value: str = "-", hint: str = "",
                 icon_name: Optional[str] = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(4)

        head = QHBoxLayout()
        head.setSpacing(6)
        self._icon_name = icon_name
        # Never show() / setVisible(True) a widget that has no parent yet: on Windows
        # it opens as its own window for a moment - a flicker at start-up. Hide
        # when needed; a child shows with its parent anyway.
        self._icon = QLabel(self)
        if not icon_name:
            self._icon.hide()
        head.addWidget(self._icon)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("kpiLabel")
        head.addWidget(self.title_label, 1)
        root.addLayout(head)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("kpiValue")
        root.addWidget(self.value_label)

        self.hint_label = QLabel(hint or " ")
        self.hint_label.setObjectName("kpiHint")
        root.addWidget(self.hint_label)
        self._paint_icon()
        theme.changed.connect(self._paint_icon)

    def _paint_icon(self) -> None:
        if self._icon_name:
            self._icon.setPixmap(icons.pixmap(self._icon_name, theme.color("text_muted"), 15))

    def set_value(self, value: str, tone: Optional[str] = None) -> None:
        self.value_label.setText(value)
        set_tone(self.value_label, tone)

    def set_hint(self, text: str, tone: Optional[str] = None) -> None:
        self.hint_label.setText(text or " ")
        set_tone(self.hint_label, tone)
