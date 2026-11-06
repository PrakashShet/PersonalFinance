"""Add / edit dialog for a bank, cash, wallet or credit-card account.

Reusable for both create and edit: pass an existing ``Account`` to pre-fill
the form (edit mode), or pass nothing to start blank (add mode). On accept,
call :meth:`get_account` to read the populated model back out.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
)

from config.constants import AccountType
from models.account import Account

# Human-readable labels for each account type, in display order.
_TYPE_LABELS = {
    AccountType.SAVINGS.value: "Savings",
    AccountType.CURRENT.value: "Current",
    AccountType.SALARY.value: "Salary",
    AccountType.CASH.value: "Cash",
    AccountType.WALLET.value: "Wallet (PhonePe / GPay / Paytm)",
    AccountType.CREDIT_CARD.value: "Credit Card",
}


class AccountDialog(QDialog):
    """Modal form for creating or editing an :class:`Account`."""

    def __init__(self, account: Optional[Account] = None, parent=None) -> None:
        super().__init__(parent)
        self._editing = account is not None
        # Work on a copy so cancelling never mutates the caller's object.
        self._account = (
            Account(**account.to_dict()) if account is not None else Account()
        )

        self.setWindowTitle("Edit Account" if self._editing else "Add Account")
        self.setModal(True)
        self.setMinimumWidth(420)

        self._build()
        self._load(self._account)

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. HDFC Salary Account")

        self.type_combo = QComboBox()
        for value, label in _TYPE_LABELS.items():
            self.type_combo.addItem(label, value)

        self.institution_edit = QLineEdit()
        self.institution_edit.setPlaceholderText("e.g. HDFC Bank (optional)")

        self.number_edit = QLineEdit()
        self.number_edit.setPlaceholderText("e.g. XXXX1234 (optional)")

        self.opening_spin = self._money_spin()
        self.current_spin = self._money_spin()

        self.currency_combo = QComboBox()
        self.currency_combo.addItems(["INR", "USD", "EUR", "GBP", "AED"])

        # Contact & KYC
        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("Registered mobile (optional)")
        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText("Registered email (optional)")
        self.ifsc_edit = QLineEdit()
        self.ifsc_edit.setPlaceholderText("e.g. HDFC0001234 (optional)")
        self.bank_address_edit = QPlainTextEdit()
        self.bank_address_edit.setPlaceholderText("Branch / bank address (optional)")
        self.bank_address_edit.setFixedHeight(56)
        self.personal_address_edit = QPlainTextEdit()
        self.personal_address_edit.setPlaceholderText(
            "Your address on record with the bank (optional)"
        )
        self.personal_address_edit.setFixedHeight(56)

        # Linked-account flags
        self.demat_check = QCheckBox("Demat account enabled")
        self.investment_check = QCheckBox("Investment account enabled")

        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText("Optional notes")
        self.notes_edit.setFixedHeight(70)

        form.addRow("Name *", self.name_edit)
        form.addRow("Type", self.type_combo)
        form.addRow("Institution", self.institution_edit)
        form.addRow("Account number", self.number_edit)
        form.addRow("Opening balance", self.opening_spin)
        form.addRow("Current balance", self.current_spin)
        form.addRow("Currency", self.currency_combo)

        form.addRow(self._section("Contact & KYC"))
        form.addRow("Phone", self.phone_edit)
        form.addRow("Email", self.email_edit)
        form.addRow("IFSC code", self.ifsc_edit)
        form.addRow("Bank address", self.bank_address_edit)
        form.addRow("Personal address", self.personal_address_edit)

        form.addRow(self._section("Linked accounts"))
        form.addRow("", self.demat_check)
        form.addRow("", self.investment_check)

        form.addRow(self._section("Other"))
        form.addRow("Notes", self.notes_edit)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    @staticmethod
    def _money_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        # Credit cards can carry negative available balance; allow it.
        spin.setRange(-1_000_000_000.0, 1_000_000_000.0)
        spin.setDecimals(2)
        spin.setGroupSeparatorShown(True)
        spin.setSingleStep(1000.0)
        return spin

    # --------------------------------------------------------------- values
    def _load(self, account: Account) -> None:
        self.name_edit.setText(account.name or "")
        idx = self.type_combo.findData(account.account_type)
        self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.institution_edit.setText(account.institution or "")
        self.number_edit.setText(account.account_number or "")
        self.opening_spin.setValue(float(account.opening_balance or 0.0))
        self.current_spin.setValue(float(account.current_balance or 0.0))
        cidx = self.currency_combo.findText(account.currency or "INR")
        self.currency_combo.setCurrentIndex(cidx if cidx >= 0 else 0)
        self.phone_edit.setText(account.phone or "")
        self.email_edit.setText(account.email or "")
        self.ifsc_edit.setText(account.ifsc_code or "")
        self.bank_address_edit.setPlainText(account.bank_address or "")
        self.personal_address_edit.setPlainText(account.personal_address or "")
        self.demat_check.setChecked(bool(account.demat_enabled))
        self.investment_check.setChecked(bool(account.investment_enabled))
        self.notes_edit.setPlainText(account.notes or "")

    def _on_accept(self) -> None:
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Account name is required.")
            self.name_edit.setFocus()
            return
        self.accept()

    def get_account(self) -> Account:
        """Return the populated account model (call after the dialog is accepted)."""
        a = self._account
        a.name = self.name_edit.text().strip()
        a.account_type = self.type_combo.currentData()
        a.institution = self.institution_edit.text().strip() or None
        a.account_number = self.number_edit.text().strip() or None
        a.opening_balance = self.opening_spin.value()
        current = self.current_spin.value()
        # New account with the current balance left at zero: mirror the
        # opening balance so the account doesn't start empty by accident.
        if not self._editing and current == 0.0:
            current = a.opening_balance
        a.current_balance = current
        a.currency = self.currency_combo.currentText()
        a.phone = self.phone_edit.text().strip() or None
        a.email = self.email_edit.text().strip() or None
        a.ifsc_code = self.ifsc_edit.text().strip().upper() or None
        a.bank_address = self.bank_address_edit.toPlainText().strip() or None
        a.personal_address = self.personal_address_edit.toPlainText().strip() or None
        a.demat_enabled = 1 if self.demat_check.isChecked() else 0
        a.investment_enabled = 1 if self.investment_check.isChecked() else 0
        a.notes = self.notes_edit.toPlainText().strip() or None
        return a
