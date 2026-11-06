"""Add / edit dialog for a transaction.

The form adapts to the selected type: the destination account is only enabled
for transfers, and the category list switches between income and expense
categories (and is disabled for transfers / investments).
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from models.transaction import Transaction
from utils.form_validation import validation_error

TYPE_OPTIONS = (
    ("income", "Income"),
    ("expense", "Expense"),
    ("transfer", "Transfer"),
    ("investment_buy", "Investment Buy"),
    ("investment_sell", "Investment Sell"),
)


class TransactionDialog(QDialog):
    def __init__(
        self,
        accounts: list,            # list of (id, name)
        income_categories: list,   # list of (id, name)
        expense_categories: list,  # list of (id, name)
        income_sources: Optional[list] = None,  # list of (id, name)
        txn: Optional[Transaction] = None,
        parent=None,
        title: Optional[str] = None,
    ) -> None:
        super().__init__(parent)
        self._accounts = accounts
        self._income_categories = income_categories
        self._expense_categories = expense_categories
        self._income_sources = income_sources or []
        self._txn = Transaction(**txn.to_dict()) if txn is not None else Transaction()
        self._editing = txn is not None

        self.setWindowTitle(title or ("Edit Transaction" if self._editing else "Add Transaction"))
        self.setModal(True)
        self.setMinimumWidth(440)
        self._build()
        self._load()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setDate(QDate.currentDate())

        self.type_combo = QComboBox()
        for value, label in TYPE_OPTIONS:
            self.type_combo.addItem(label, value)
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setRange(0.0, 1_000_000_000.0)
        self.amount_spin.setDecimals(2)
        self.amount_spin.setGroupSeparatorShown(True)
        self.amount_spin.setSingleStep(100.0)

        self.account_combo = QComboBox()
        for aid, name in self._accounts:
            self.account_combo.addItem(name, aid)

        self.counter_combo = QComboBox()
        self.counter_combo.addItem("-", None)
        for aid, name in self._accounts:
            self.counter_combo.addItem(name, aid)

        self.category_combo = QComboBox()

        self.source_combo = QComboBox()
        self.source_combo.addItem("-", None)
        for sid, name in self._income_sources:
            self.source_combo.addItem(name, sid)

        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("e.g. Grocery shopping")
        self.ref_edit = QLineEdit()
        self.ref_edit.setPlaceholderText("Reference / cheque no. (optional)")
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("comma,separated,tags (optional)")

        form.addRow("Date *", self.date_edit)
        form.addRow("Type *", self.type_combo)
        form.addRow("Amount *", self.amount_spin)
        form.addRow("Account *", self.account_combo)
        form.addRow("To account", self.counter_combo)
        form.addRow("Category", self.category_combo)
        form.addRow("Income source", self.source_combo)
        form.addRow("Description", self.desc_edit)
        form.addRow("Reference", self.ref_edit)
        form.addRow("Tags", self.tags_edit)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _current_type(self) -> str:
        return self.type_combo.currentData()

    def _populate_categories(self) -> None:
        t = self._current_type()
        self.category_combo.clear()
        self.category_combo.addItem("-", None)
        if t == "income":
            source = self._income_categories
        elif t == "expense":
            source = self._expense_categories
        else:
            source = []
        for cid, name in source:
            self.category_combo.addItem(name, cid)
        self.category_combo.setEnabled(bool(source))

    def _on_type_changed(self) -> None:
        t = self._current_type()
        is_transfer = t == "transfer"
        self.counter_combo.setEnabled(is_transfer)
        if not is_transfer:
            self.counter_combo.setCurrentIndex(0)
        # Income source only applies to income transactions
        is_income = t == "income"
        self.source_combo.setEnabled(is_income and bool(self._income_sources))
        if not is_income:
            self.source_combo.setCurrentIndex(0)
        self._populate_categories()

    # --------------------------------------------------------------- values
    def _load(self) -> None:
        t = self._txn
        if t.txn_date:
            d = QDate.fromString(t.txn_date, "yyyy-MM-dd")
            if d.isValid():
                self.date_edit.setDate(d)
        # type
        tidx = self.type_combo.findData(t.txn_type or "expense")
        self.type_combo.setCurrentIndex(tidx if tidx >= 0 else 0)
        self._on_type_changed()  # sync dependent widgets

        self.amount_spin.setValue(float(t.amount or 0.0))
        aidx = self.account_combo.findData(t.account_id)
        if aidx >= 0:
            self.account_combo.setCurrentIndex(aidx)
        cidx = self.counter_combo.findData(t.counter_account_id)
        self.counter_combo.setCurrentIndex(cidx if cidx >= 0 else 0)
        catidx = self.category_combo.findData(t.category_id)
        self.category_combo.setCurrentIndex(catidx if catidx >= 0 else 0)
        sidx = self.source_combo.findData(t.income_source_id)
        self.source_combo.setCurrentIndex(sidx if sidx >= 0 else 0)
        self.desc_edit.setText(t.description or "")
        self.ref_edit.setText(t.reference_no or "")
        self.tags_edit.setText(t.tags or "")

    def _on_accept(self) -> None:
        amount_err = validation_error(
            "Amount", self.amount_spin.value(), kind="money"
        )
        if amount_err:
            QMessageBox.warning(self, "Validation", amount_err)
            return
        if self.account_combo.currentData() is None:
            QMessageBox.warning(self, "Validation", "Please select an account.")
            return
        if self._current_type() == "transfer":
            counter = self.counter_combo.currentData()
            if counter is None:
                QMessageBox.warning(self, "Validation", "Select a destination account.")
                return
            if counter == self.account_combo.currentData():
                QMessageBox.warning(self, "Validation", "Transfer accounts must differ.")
                return
        self.accept()

    def get_transaction(self) -> Transaction:
        t = self._txn
        t.txn_date = self.date_edit.date().toString("yyyy-MM-dd")
        t.txn_type = self._current_type()
        t.amount = float(self.amount_spin.value())
        t.account_id = self.account_combo.currentData()
        t.counter_account_id = (
            self.counter_combo.currentData() if t.txn_type == "transfer" else None
        )
        t.category_id = self.category_combo.currentData()
        t.income_source_id = (
            self.source_combo.currentData() if t.txn_type == "income" else None
        )
        t.description = self.desc_edit.text().strip() or None
        t.reference_no = self.ref_edit.text().strip() or None
        t.tags = self.tags_edit.text().strip() or None
        return t
