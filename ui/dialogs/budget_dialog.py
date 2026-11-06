"""Add / edit a budget: a category, a limit, and whether it is per month or
per year. Suggests a starting limit from what was actually spent recently."""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from models.budget import Budget
from services.budget_service import MONTHLY, Suggestion
from ui.helpers.budget_text import PERIOD_OPTIONS, money
from ui.widgets.common import SegmentedControl, button, label, set_tone, style_button_box


class BudgetDialog(QDialog):
    def __init__(
        self,
        categories: list[tuple[int, str]],                       # expense categories
        budget: Optional[Budget] = None,
        existing: Optional[Callable[[int, str], Optional[Budget]]] = None,
        suggest: Optional[Callable[[int, str], Optional[Suggestion]]] = None,
        year_text: str = "",
        category_id: Optional[int] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._budget = budget
        self._existing = existing
        self._suggest = suggest
        self._suggested: Optional[float] = None
        self.setWindowTitle("Edit budget" if budget else "Add budget")
        self.setModal(True)
        self.setMinimumWidth(480)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)
        root.addWidget(label(self.windowTitle(), "sectionTitle"))
        root.addWidget(label("Choose a spending category and how much you're happy to spend on "
                             "it. Every expense in that category counts towards the limit.",
                             "muted", wrap=True))

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(16)

        self.category_combo = QComboBox()
        for cid, name in categories:
            self.category_combo.addItem(name, cid)
        form.addRow("Category", self.category_combo)

        self.period_seg = SegmentedControl(PERIOD_OPTIONS, MONTHLY)
        period_box = QVBoxLayout()
        period_box.setSpacing(4)
        period_box.addWidget(self.period_seg, 0, Qt.AlignmentFlag.AlignLeft)
        self.period_hint = label("", "fieldHint", wrap=True)
        period_box.addWidget(self.period_hint)
        self._year_text = year_text
        form.addRow("Limit applies", period_box)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setObjectName("amountInput")
        self.amount_spin.setDecimals(0)
        self.amount_spin.setGroupSeparatorShown(True)
        self.amount_spin.setRange(0.0, 1_000_000_000.0)
        self.amount_spin.setSingleStep(500.0)
        self.amount_spin.setPrefix("₹ ")
        self.amount_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        form.addRow("Limit", self.amount_spin)

        self.suggest_row = QWidget()
        srow = QHBoxLayout(self.suggest_row)
        srow.setContentsMargins(0, 0, 0, 0)
        srow.setSpacing(8)
        self.suggest_label = label("", "fieldHint", wrap=True)
        srow.addWidget(self.suggest_label, 1)
        self.use_btn = button("Use it", "link", on_click=self._use_suggestion)
        srow.addWidget(self.use_btn, 0, Qt.AlignmentFlag.AlignTop)
        form.addRow("", self.suggest_row)

        self.clash_label = label("", "fieldHint", wrap=True)
        form.addRow("", self.clash_label)

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Optional - e.g. includes Swiggy and Zomato")
        form.addRow("Note", self.notes_edit)
        self.form = form
        root.addLayout(form)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                               | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self._on_accept)
        box.rejected.connect(self.reject)
        style_button_box(box)
        root.addWidget(box)

        if budget is not None:
            idx = self.category_combo.findData(budget.category_id)
            self.category_combo.setCurrentIndex(max(idx, 0))
            self.period_seg.set_current(budget.period)
            self.amount_spin.setValue(float(budget.amount or 0.0))
            self.notes_edit.setText(budget.notes or "")
        elif category_id is not None:
            idx = self.category_combo.findData(category_id)
            self.category_combo.setCurrentIndex(max(idx, 0))

        self.category_combo.currentIndexChanged.connect(lambda _i: self._refresh())
        self.period_seg.changed.connect(lambda _k: self._refresh())
        self._refresh()
        self.amount_spin.setFocus()
        self.amount_spin.selectAll()

    # ------------------------------------------------------------- helpers
    def _period(self) -> str:
        return self.period_seg.current() or MONTHLY

    def _refresh(self) -> None:
        cid = self.category_combo.currentData()
        period = self._period()
        name = self.category_combo.currentText()
        unit = "month" if period == MONTHLY else "year"
        self.period_hint.setText("Counts expenses in each calendar month." if period == MONTHLY
                                 else f"Counts expenses in each year, {self._year_text}."
                                 if self._year_text else "Counts expenses in each year.")

        suggestion = self._suggest(cid, period) if (self._suggest and cid is not None) else None
        self._suggested = suggestion.amount if suggestion else None
        if suggestion:
            self.suggest_label.setText(
                f"You've been spending about {money(suggestion.amount)} a {unit} on {name} "
                f"(from {suggestion.months} month{'' if suggestion.months == 1 else 's'} of records).")
            self.use_btn.setText(f"Use {money(suggestion.amount)}")
        self.form.setRowVisible(self.suggest_row, suggestion is not None)

        other = self._existing(cid, period) if (self._existing and cid is not None) else None
        if other is not None and (self._budget is None or other.id != self._budget.id):
            if self._budget is None:
                text = (f"{name} already has a {period} limit of {money(other.amount)}. "
                        "Saving replaces it.")
                tone = "warning"
                # Start from what's there, so replacing it never silently drops the note.
                if self.amount_spin.value() == 0:
                    self.amount_spin.setValue(float(other.amount or 0.0))
                if not self.notes_edit.text() and other.notes:
                    self.notes_edit.setText(other.notes)
            else:
                text = f"{name} already has a {period} limit. Edit that one instead."
                tone = "negative"
            self.clash_label.setText(text)
            set_tone(self.clash_label, tone)
            self.form.setRowVisible(self.clash_label, True)
        else:
            self.form.setRowVisible(self.clash_label, False)
        self.adjustSize()

    def _use_suggestion(self) -> None:
        if self._suggested:
            self.amount_spin.setValue(self._suggested)

    def _on_accept(self) -> None:
        if self.category_combo.currentData() is None:
            QMessageBox.warning(self, "Please check", "Choose a spending category.")
            return
        if self.amount_spin.value() <= 0:
            QMessageBox.warning(self, "Please check", "Enter a limit greater than zero.")
            self.amount_spin.setFocus()
            return
        self.accept()

    def values(self) -> dict:
        return {
            "category_id": self.category_combo.currentData(),
            "period": self._period(),
            "amount": float(self.amount_spin.value()),
            "notes": self.notes_edit.text().strip() or None,
        }

    def get_budget(self) -> Budget:
        """The edited budget (keeps its id); for a new one use :meth:`values`."""
        b = Budget(**self._budget.to_dict()) if self._budget is not None else Budget()
        v = self.values()
        b.category_id, b.period, b.amount, b.notes = v["category_id"], v["period"], v["amount"], v["notes"]
        return b
