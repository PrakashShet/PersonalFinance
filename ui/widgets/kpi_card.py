"""Reusable KPI card for dashboard."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout


class KpiCard(QFrame):
    def __init__(self, title: str, value: str) -> None:
        super().__init__()
        self.setObjectName("kpiCard")
        self.setFrameShape(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(self)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("kpiTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.value_label = QLabel(value)
        self.value_label.setObjectName("kpiValue")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)
