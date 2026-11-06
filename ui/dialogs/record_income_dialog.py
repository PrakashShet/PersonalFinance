"""Record (or edit) a month's actual income for an income source.

Logs the amount actually received in a given month and — when a deposit account
is selected and "Post to ledger" is ticked — creates a matching income
transaction so the account balance stays correct.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from models.income import IncomeSource
from models.income_entry import IncomeEntry
from utils.formatters import fmt_inr


class RecordIncomeDialog(QDialog):
    def __init__(
        self,
        source: IncomeSource,
        accounts: list,                       # list of (id, name)
        expected_net: float = 0.0,
        entry: Optional[IncomeEntry] = None,  # editing an existing month
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._source = source
        self._accounts = accounts
        self._expected = expected_net
        self._entry = entry
        self._editing = entry is not None

        self.setWindowTitle(
            f"Edit Income — {source.name}" if self._editing
            else f"Record Income — {source.name}"
        )
        self.setModal(True)
        self.setMinimumWidth(420)
        self._build()
        self._load()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        # Period (month). Day is irrelevant; we store 'YYYY-MM'.
        self.period_edit = QDateEdit()
        self.period_edit.setCalendarPopup(True)
        self.period_edit.setDisplayFormat("MMMM yyyy")
        self.period_edit.setDate(QDate.currentDate())

        self.expected_label = QLabel(fmt_inr(self._expected) if self._expected else "—")

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.0, 1_000_000_000.0)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setGroupSeparatorShown(True)
        self.amount_spin.setSingleStep(1000.0)
        self.amount_spin.setPrefix("₹ ")
        self.amount_spin.setValue(self._expected or 0.0)

        self.received_edit = QDateEdit()
        self.received_edit.setCalendarPopup(True)
        self.received_edit.setDisplayFormat("yyyy-MM-dd")
        self.received_edit.setDate(QDate.currentDate())

        self.account_combo = QComboBox()
        self.account_combo.addItem("— Not linked —", None)
        for aid, name in self._accounts:
            self.account_combo.addItem(name, aid)
        # Default to the source's deposit account.
        default_idx = self.account_combo.findData(self._source.deposit_account_id)
        if default_idx >= 0:
            self.account_combo.setCurrentIndex(default_idx)

        self.post_check = QCheckBox("Post to ledger & update account balance")
        self.post_check.setChecked(True)
        self.account_combo.currentIndexChanged.connect(self._sync_post_enabled)

        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText("Optional notes (e.g. bonus included)")

        form.addRow("Month *", self.period_edit)
        form.addRow("Expected (net)", self.expected_label)
        form.addRow("Actual received *", self.amount_spin)
        form.addRow("Received on", self.received_edit)
        form.addRow("Deposit account", self.account_combo)
        form.addRow("", self.post_check)
        form.addRow("Notes", self.notes_edit)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._sync_post_enabled()

    def _sync_post_enabled(self) -> None:
        has_account = self.account_combo.currentData() is not None
        self.post_check.setEnabled(has_account)
        if not has_account:
            self.post_check.setChecked(False)

    # --------------------------------------------------------------- values
    def _load(self) -> None:
        if not self._editing:
            return
        e = self._entry
        d = QDate.fromString((e.period_month or "") + "-01", "yyyy-MM-dd")
        if d.isValid():
            self.period_edit.setDate(d)
        self.amount_spin.setValue(float(e.actual_amount or 0.0))
        if e.received_date:
            rd = QDate.fromString(e.received_date, "yyyy-MM-dd")
            if rd.isValid():
                self.received_edit.setDate(rd)
        aidx = self.account_combo.findData(e.account_id)
        if aidx >= 0:
            self.account_combo.setCurrentIndex(aidx)
        self.post_check.setChecked(bool(e.transaction_id))
        self.notes_edit.setText(e.notes or "")
        self._sync_post_enabled()

    def _on_accept(self) -> None:
        if self.amount_spin.value() <= 0:
            QMessageBox.warning(self, "Validation", "Actual amount must be greater than zero.")
            return
        self.accept()

    def get_values(self) -> dict:
        return {
            "period_month": self.period_edit.date().toString("yyyy-MM"),
            "actual_amount": float(self.amount_spin.value()),
            "received_date": self.received_edit.date().toString("yyyy-MM-dd"),
            "account_id": self.account_combo.currentData(),
            "post_to_ledger": self.post_check.isChecked(),
            "notes": self.notes_edit.text().strip() or None,
        }
