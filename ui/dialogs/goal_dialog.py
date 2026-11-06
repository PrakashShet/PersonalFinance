"""Add / Edit Goal dialog."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt

from models.goal import Goal
from utils.form_validation import validation_error
from utils.formatters import fmt_inr
from ui.widgets.common import style_button_box
from ui.widgets.date_field import DateField


STATUSES = [
    ("active",    "Active"),
    ("paused",    "Paused"),
    ("achieved",  "Achieved"),
    ("abandoned", "Abandoned"),
]

PRIORITY_LABELS = {1: "1 - Critical", 2: "2 - High", 3: "3 - Medium",
                   4: "4 - Low", 5: "5 - Nice-to-have"}


def _money_spin(max_val: float = 50_00_00_000) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0, max_val)
    s.setDecimals(2)
    s.setSingleStep(10_000)
    s.setGroupSeparatorShown(True)
    s.setPrefix("₹ ")
    return s


def _rate_spin(default: float = 10.0) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(0, 50)
    s.setDecimals(2)
    s.setSuffix(" %")
    s.setValue(default)
    return s


class GoalDialog(QDialog):
    """Modal dialog for creating or editing a Goal."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        goal: Optional[Goal] = None,
        holdings: Optional[list] = None,    # list of (id, name, current_value)
        linked_ids: Optional[list] = None,  # holding ids already linked
    ) -> None:
        super().__init__(parent)
        self._goal = goal
        self._holdings = holdings or []
        self._linked_ids = set(linked_ids or [])
        self._holding_checks: dict[int, QCheckBox] = {}
        self._editing = goal is not None
        self.setWindowTitle("Edit Goal" if self._editing else "Add Goal")
        self.setMinimumWidth(460)
        self.setModal(True)
        self._build()
        if self._editing:
            self._populate(goal)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)

        # -- Core --
        core = QGroupBox("Goal")
        cf = QFormLayout(core)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Emergency Fund, House Down Payment")
        cf.addRow("Name *", self.name_edit)

        self.target_spin = _money_spin()
        cf.addRow("Target Amount *", self.target_spin)

        self.current_spin = _money_spin()
        cf.addRow("Current Amount", self.current_spin)

        self.target_date = DateField(QDate.currentDate().addYears(3))
        cf.addRow("Target Date", self.target_date)

        # Priority slider + label
        pri_row = QHBoxLayout()
        self.priority_slider = QSlider(Qt.Orientation.Horizontal)
        self.priority_slider.setRange(1, 5)
        self.priority_slider.setValue(3)
        self.priority_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.priority_slider.setTickInterval(1)
        self.priority_label = QLabel(PRIORITY_LABELS[3])
        self.priority_slider.valueChanged.connect(
            lambda v: self.priority_label.setText(PRIORITY_LABELS[v]))
        pri_row.addWidget(self.priority_slider, 1)
        pri_row.addWidget(self.priority_label)
        cf.addRow("Priority", pri_row)

        self.status_combo = QComboBox()
        for key, label in STATUSES:
            self.status_combo.addItem(label, key)
        cf.addRow("Status", self.status_combo)

        root.addWidget(core)

        # -- Assumptions --
        assume = QGroupBox("Return & Inflation Assumptions")
        af = QFormLayout(assume)

        self.return_spin = _rate_spin(10.0)
        af.addRow("Expected Return (p.a.)", self.return_spin)

        self.inflation_spin = _rate_spin(6.0)
        af.addRow("Inflation Rate (p.a.)", self.inflation_spin)

        root.addWidget(assume)

        # -- Funded by holdings (optional) --
        if self._holdings:
            link_group = QGroupBox("Funded by Holdings (optional)")
            lg = QVBoxLayout(link_group)
            note = QLabel(
                "Tick the investments that fund this goal. When any are linked, "
                "the goal's saved amount is computed from their current value."
            )
            note.setObjectName("tileFlags")
            note.setWordWrap(True)
            lg.addWidget(note)

            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.Shape.NoFrame)
            scroll.setMaximumHeight(160)
            inner = QWidget()
            il = QVBoxLayout(inner)
            il.setContentsMargins(0, 0, 0, 0)
            il.setSpacing(4)
            for hid, name, value in self._holdings:
                cb = QCheckBox(f"{name}  —  {fmt_inr(value, compact=True)}")
                cb.setChecked(hid in self._linked_ids)
                self._holding_checks[hid] = cb
                il.addWidget(cb)
            il.addStretch()
            scroll.setWidget(inner)
            lg.addWidget(scroll)
            root.addWidget(link_group)

        # -- Notes --
        notes_group = QGroupBox("Notes")
        nl = QVBoxLayout(notes_group)
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(70)
        nl.addWidget(self.notes_edit)
        root.addWidget(notes_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        style_button_box(buttons)
        root.addWidget(buttons)

    # ------------------------------------------------------------------
    def _on_accept(self) -> None:
        name_err = validation_error("Name", self.name_edit.text(), kind="text")
        if name_err:
            QMessageBox.warning(self, "Validation", name_err)
            self.name_edit.setFocus()
            return
        target_err = validation_error("Target amount", self.target_spin.value(), kind="money")
        if target_err:
            QMessageBox.warning(self, "Validation", target_err)
            self.target_spin.setFocus()
            return
        self.accept()

    def _populate(self, g: Goal) -> None:
        self.name_edit.setText(g.name or "")
        self.target_spin.setValue(g.target_amount or 0)
        self.current_spin.setValue(g.current_amount or 0)
        self.target_date.set_iso(g.target_date)
        self.priority_slider.setValue(g.priority or 3)
        idx = self.status_combo.findData(g.status or "active")
        if idx >= 0:
            self.status_combo.setCurrentIndex(idx)
        self.return_spin.setValue((g.expected_return or 0.10) * 100)
        self.inflation_spin.setValue((g.inflation_rate or 0.06) * 100)
        if g.notes:
            self.notes_edit.setPlainText(g.notes)

    def selected_holding_ids(self) -> list[int]:
        return [hid for hid, cb in self._holding_checks.items() if cb.isChecked()]

    def get_goal(self) -> Goal:
        return Goal(
            id=self._goal.id if self._editing else None,
            name=self.name_edit.text().strip(),
            target_amount=self.target_spin.value(),
            current_amount=self.current_spin.value(),
            target_date=self.target_date.iso(),
            priority=self.priority_slider.value(),
            status=self.status_combo.currentData(),
            expected_return=self.return_spin.value() / 100.0,
            inflation_rate=self.inflation_spin.value() / 100.0,
            notes=self.notes_edit.toPlainText().strip() or None,
        )
