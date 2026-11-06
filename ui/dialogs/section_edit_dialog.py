"""Generic edit dialog for one account detail section.

Builds a form from a ``Section`` spec (config.account_fields), loads values
from an Account, and writes edited values back. Used both for creating a new
account (the "Account Details" section) and for editing any one section.

Fields marked ``in_form=False`` (the opening balance) are never edited here -
balances move through the ledger, see services/account_service.py.
"""
from __future__ import annotations

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
    QSpinBox,
    QVBoxLayout,
)

from config.account_fields import Field, Section
from models.account import Account
from ui.widgets.common import label, style_button_box
from utils.form_validation import validation_error


class SectionEditDialog(QDialog):
    """Edit the fields of one section on a copy of an Account."""

    def __init__(
        self,
        account: Account,
        section: Section,
        parent=None,
        title: str | None = None,
        creating: bool = False,
    ) -> None:
        super().__init__(parent)
        # Work on a copy so cancelling never mutates the caller's object.
        self._account = Account(**account.to_dict())
        self._section = section
        self._creating = creating
        self._widgets: dict[str, object] = {}

        self.setWindowTitle(title or f"Edit {section.title.lower()}")
        self.setModal(True)
        self.setMinimumWidth(460)
        self._build()
        self._load()

    def _fields(self) -> list[Field]:
        return [f for f in self._section.fields if f.in_form]

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)
        root.addWidget(label(self.windowTitle(), "sectionTitle"))
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(16)

        for f in self._fields():
            widget = self._make_widget(f)
            self._widgets[f.attr] = widget
            text = f.label + (" *" if f.required else "")
            if f.attr == "current_balance" and self._creating:
                text = "Balance today"
            form.addRow(text, widget)
            if f.hint and not self._creating:
                hint = QLabel(f.hint)
                hint.setObjectName("fieldHint")
                hint.setWordWrap(True)
                form.addRow("", hint)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        style_button_box(buttons)
        root.addWidget(buttons)

    def _make_widget(self, f: Field):
        if f.kind == "text":
            w = QLineEdit()
            if f.placeholder:
                w.setPlaceholderText(f.placeholder)
            return w
        if f.kind == "multiline":
            w = QPlainTextEdit()
            w.setFixedHeight(64)
            if f.placeholder:
                w.setPlaceholderText(f.placeholder)
            return w
        if f.kind in ("money", "percent"):
            w = QDoubleSpinBox()
            w.setDecimals(2)
            w.setGroupSeparatorShown(True)
            if f.kind == "percent":
                w.setRange(0.0, 100.0)
                w.setSingleStep(0.25)
                w.setSuffix(" %")
            else:
                w.setRange(-1_000_000_000.0, 1_000_000_000.0)
                w.setSingleStep(1000.0)
                w.setPrefix("₹ ")
            return w
        if f.kind in ("int", "day"):
            w = QSpinBox()
            w.setRange(0, 31 if f.kind == "day" else 1_000_000)
            return w
        if f.kind == "combo":
            w = QComboBox()
            if not f.required:
                w.addItem("-", None)
            for value, text in f.options:
                w.addItem(text, value)
            return w
        if f.kind == "checkbox":
            return QCheckBox()
        return QLineEdit()

    # --------------------------------------------------------------- values
    def _load(self) -> None:
        for f in self._fields():
            w = self._widgets[f.attr]
            value = getattr(self._account, f.attr, None)
            if f.kind == "text":
                w.setText("" if value is None else str(value))
            elif f.kind == "multiline":
                w.setPlainText("" if value is None else str(value))
            elif f.kind in ("money", "percent"):
                w.setValue(float(value or 0.0))
            elif f.kind in ("int", "day"):
                w.setValue(int(value or 0))
            elif f.kind == "combo":
                idx = w.findData(value)
                w.setCurrentIndex(idx if idx >= 0 else 0)
            elif f.kind == "checkbox":
                w.setChecked(bool(value))
        currency = self._widgets.get("currency")
        balance = self._widgets.get("current_balance")
        if isinstance(currency, QComboBox) and isinstance(balance, QDoubleSpinBox):
            def _prefix() -> None:
                code = currency.currentData() or "INR"
                balance.setPrefix("₹ " if code == "INR" else f"{code} ")
            currency.currentIndexChanged.connect(lambda _i: _prefix())
            _prefix()

    def _on_accept(self) -> None:
        for f in self._fields():
            if not f.required:
                continue
            w = self._widgets[f.attr]
            if isinstance(w, QLineEdit):
                err = validation_error(f.label, w.text(), kind="text")
            elif isinstance(w, QComboBox):
                err = (
                    validation_error(f.label, w.currentData(), kind="text")
                    if w.currentData() is None
                    else None
                )
            else:
                err = None
            if err:
                QMessageBox.warning(self, "Please check", err)
                w.setFocus()
                return
        self.accept()

    def get_account(self) -> Account:
        """Return the account copy with this section's values applied."""
        a = self._account
        for f in self._fields():
            w = self._widgets[f.attr]
            if f.kind == "text":
                setattr(a, f.attr, w.text().strip() or None)
            elif f.kind == "multiline":
                setattr(a, f.attr, w.toPlainText().strip() or None)
            elif f.kind in ("money", "percent"):
                setattr(a, f.attr, float(w.value()))
            elif f.kind in ("int", "day"):
                setattr(a, f.attr, int(w.value()))
            elif f.kind == "combo":
                setattr(a, f.attr, w.currentData())
            elif f.kind == "checkbox":
                setattr(a, f.attr, 1 if w.isChecked() else 0)
        return a
