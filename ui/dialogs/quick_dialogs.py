"""Small single-purpose dialogs: update a balance, log a due payment, add a
reminder. Each asks for the minimum and pre-fills everything it can."""
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

from ui.widgets.common import label, style_button_box
from utils.formatters import fmt_money


def _amount_spin(value: float = 0.0, allow_negative: bool = False, prefix: str = "₹ ") -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setObjectName("amountInput")
    s.setDecimals(2)
    s.setGroupSeparatorShown(True)
    s.setRange(-1_000_000_000.0 if allow_negative else 0.0, 1_000_000_000.0)
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
    s.setPrefix(prefix)
    s.setValue(value)
    return s


def _date_edit(iso: Optional[str] = None) -> QDateEdit:
    d = QDateEdit()
    d.setCalendarPopup(True)
    d.setDisplayFormat("dd MMM yyyy")
    qd = QDate.fromString((iso or "")[:10], "yyyy-MM-dd")
    d.setDate(qd if qd.isValid() else QDate.currentDate())
    return d


def _buttons(dialog: QDialog, on_accept) -> QDialogButtonBox:
    box = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
    box.accepted.connect(on_accept)
    box.rejected.connect(dialog.reject)
    style_button_box(box)
    return box


class UpdateBalanceDialog(QDialog):
    """"What's in this account today?" The difference is recorded as an adjustment."""

    def __init__(self, account_name: str, current: float, currency: str = "INR", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Update balance")
        self.setModal(True)
        self.setMinimumWidth(420)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)
        root.addWidget(label(f"Update balance - {account_name}", "sectionTitle"))
        root.addWidget(label(
            f"Currently {fmt_money(current, currency)}. Enter what the account holds today; "
            "the difference is recorded as a balance adjustment, so your history stays correct.",
            "muted", wrap=True))
        prefix = "₹ " if (currency or "INR") == "INR" else f"{currency} "
        self.spin = _amount_spin(current, allow_negative=True, prefix=prefix)
        root.addWidget(self.spin)
        root.addWidget(_buttons(self, self.accept))
        self.spin.setFocus()
        self.spin.selectAll()

    def value(self) -> float:
        return float(self.spin.value())


class LogPaymentDialog(QDialog):
    """Confirm a due SIP / EMI / premium: amount, date and account pre-filled."""

    def __init__(self, title: str, amount: float, due_date: str, accounts: list,
                 account_id: Optional[int], note: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(440)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)
        root.addWidget(label(title, "sectionTitle"))
        if note:
            root.addWidget(label(note, "muted", wrap=True))
        self.amount = _amount_spin(amount)
        root.addWidget(self.amount)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(16)
        self.account = QComboBox()
        for aid, name in accounts:
            self.account.addItem(name, aid)
        idx = self.account.findData(account_id)
        if idx >= 0:
            self.account.setCurrentIndex(idx)
        form.addRow("Paid from", self.account)
        self.date = _date_edit(min(due_date, QDate.currentDate().toString("yyyy-MM-dd")))
        form.addRow("Date", self.date)
        root.addLayout(form)
        root.addWidget(_buttons(self, self._on_accept))

    def _on_accept(self) -> None:
        if self.amount.value() <= 0:
            QMessageBox.warning(self, "Please check", "Enter an amount greater than zero.")
            return
        if self.account.currentData() is None:
            QMessageBox.warning(self, "Please check", "Add an account first, then log this payment.")
            return
        self.accept()

    def values(self) -> tuple[float, str, int]:
        return (float(self.amount.value()),
                self.date.date().toString("yyyy-MM-dd"),
                self.account.currentData())


class ReminderDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add reminder")
        self.setModal(True)
        self.setMinimumWidth(420)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)
        root.addWidget(label("Add reminder", "sectionTitle"))
        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(16)
        self.title = QLineEdit()
        self.title.setPlaceholderText("e.g. Renew car insurance")
        form.addRow("What", self.title)
        self.date = _date_edit()
        form.addRow("When", self.date)
        self.amount = _amount_spin()
        self.amount.setObjectName("")
        form.addRow("Amount (optional)", self.amount)
        self.notes = QLineEdit()
        form.addRow("Note", self.notes)
        root.addLayout(form)
        root.addWidget(_buttons(self, self._on_accept))

    def _on_accept(self) -> None:
        if not self.title.text().strip():
            QMessageBox.warning(self, "Please check", "Give the reminder a title.")
            return
        self.accept()

    def values(self) -> dict:
        return {
            "title": self.title.text().strip(),
            "due_date": self.date.date().toString("yyyy-MM-dd"),
            "amount": float(self.amount.value()) or None,
            "notes": self.notes.text().strip() or None,
        }
