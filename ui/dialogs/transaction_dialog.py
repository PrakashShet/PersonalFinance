"""Add / edit a transaction - type first, then only the fields that matter.

Expense: amount, paid from, category, date, note.
Income: amount, received in, category, date, note (+ income source under More).
Transfer: amount, from, to, date, note.
Investment: buy or sell, amount, account, which investment, date, note.
Adjustments (opening balances, corrections) can be edited but not created
here - use "Update balance" on the account instead.

For an expense in a category with a budget, a line under the category says
what is left - and, once an amount is typed, what would be left after it.
"""
from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from models.transaction import Transaction
from ui.widgets.common import Badge, SegmentedControl, button, label, set_tone, style_button_box
from utils.logger import get_logger

log = get_logger(__name__)

# (category_id, txn_date, account_id, amount) -> (text, tone) or None
BudgetHint = Callable[[int, str, Optional[int], float], Optional[tuple[str, str]]]

TYPE_OPTIONS = (
    ("expense", "Expense"),
    ("income", "Income"),
    ("transfer", "Transfer"),
    ("investment", "Investment"),
)
_INVEST = (("investment_buy", "Buy / invest"), ("investment_sell", "Sell / withdraw"))
_ACCOUNT_LABEL = {
    "expense": "Paid from",
    "income": "Received in",
    "transfer": "From",
    "investment_buy": "Paid from",
    "investment_sell": "Received in",
    "adjustment": "Account",
}
_DESC_HINT = {
    "expense": "What was it for? e.g. Groceries at DMart",
    "income": "e.g. November salary",
    "transfer": "e.g. Move to savings",
    "investment_buy": "e.g. Monthly SIP",
    "investment_sell": "e.g. Partial redemption",
    "adjustment": "Why the balance changed",
}


class TransactionDialog(QDialog):
    def __init__(
        self,
        accounts: list,                       # [(id, name)]
        income_categories: list,              # [(id, name)]
        expense_categories: list,             # [(id, name)]
        income_sources: Optional[list] = None,
        txn: Optional[Transaction] = None,
        parent=None,
        title: Optional[str] = None,
        holdings: Optional[list] = None,      # [(id, name)]
        default_type: str = "expense",
        default_account_id: Optional[int] = None,
        default_date: Optional[str] = None,
        budget_hint: Optional[BudgetHint] = None,
    ) -> None:
        super().__init__(parent)
        self._budget_hint = budget_hint
        self._accounts = accounts
        self._income_categories = income_categories
        self._expense_categories = expense_categories
        self._income_sources = income_sources or []
        self._holdings = holdings or []
        self._txn = Transaction(**txn.to_dict()) if txn is not None else Transaction()
        self._editing = txn is not None
        self._is_adjustment = self._txn.txn_type == "adjustment"
        self._default_type = default_type
        self._default_account_id = default_account_id
        self._default_date = default_date
        self.add_another = False

        self.setWindowTitle(title or ("Edit transaction" if self._editing else "Add transaction"))
        self.setModal(True)
        self.setMinimumWidth(500)
        self._build()
        self._load()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(14)
        root.addWidget(label(self.windowTitle(), "sectionTitle"))

        self.type_seg = SegmentedControl(TYPE_OPTIONS, "expense")
        self.type_seg.changed.connect(lambda _k: self._on_type_changed())
        self.adjust_badge = Badge("Balance adjustment", "info")
        root.addWidget(self.adjust_badge if self._is_adjustment else self.type_seg)

        self.invest_seg = SegmentedControl(_INVEST, "investment_buy")
        self.invest_seg.changed.connect(lambda _k: self._on_type_changed())
        root.addWidget(self.invest_seg)

        self.amount_spin = QDoubleSpinBox()
        self.amount_spin.setObjectName("amountInput")
        self.amount_spin.setDecimals(2)
        self.amount_spin.setGroupSeparatorShown(True)
        self.amount_spin.setSingleStep(100.0)
        self.amount_spin.setPrefix("₹ ")
        if self._is_adjustment:
            self.amount_spin.setRange(-1_000_000_000.0, 1_000_000_000.0)
        else:
            self.amount_spin.setRange(0.0, 1_000_000_000.0)
        self.amount_spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        root.addWidget(self.amount_spin)

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(16)
        self.form = form

        self.account_combo = QComboBox()
        for aid, name in self._accounts:
            self.account_combo.addItem(name, aid)
        self.account_label = QLabel("Paid from")
        form.addRow(self.account_label, self.account_combo)

        self.counter_combo = QComboBox()
        self.counter_combo.addItem("Choose account", None)
        for aid, name in self._accounts:
            self.counter_combo.addItem(name, aid)
        form.addRow("To", self.counter_combo)

        self.category_combo = QComboBox()
        form.addRow("Category", self.category_combo)
        self.budget_label = label("", "fieldHint", wrap=True)
        form.addRow("", self.budget_label)

        self.holding_combo = QComboBox()
        self.holding_combo.addItem("Not linked", None)
        for hid, name in self._holdings:
            self.holding_combo.addItem(name, hid)
        self.holding_combo.setToolTip("Linking lets the app work out this investment's annual return.")
        form.addRow("Investment", self.holding_combo)

        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("dd MMM yyyy")
        self.date_edit.setDate(QDate.currentDate())
        form.addRow("Date", self.date_edit)

        self.desc_edit = QLineEdit()
        form.addRow("Note", self.desc_edit)
        root.addLayout(form)

        self.more_btn = button("More options", "link", on_click=self._toggle_more)
        root.addWidget(self.more_btn, 0, Qt.AlignmentFlag.AlignLeft)
        self.more = QWidget()
        more_form = QFormLayout(self.more)
        more_form.setContentsMargins(0, 0, 0, 0)
        more_form.setVerticalSpacing(10)
        more_form.setHorizontalSpacing(16)
        self.source_combo = QComboBox()
        self.source_combo.addItem("-", None)
        for sid, name in self._income_sources:
            self.source_combo.addItem(name, sid)
        self.source_label = QLabel("Income source")
        more_form.addRow(self.source_label, self.source_combo)
        self.ref_edit = QLineEdit()
        self.ref_edit.setPlaceholderText("Cheque / UPI reference (optional)")
        more_form.addRow("Reference", self.ref_edit)
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("comma, separated (optional)")
        more_form.addRow("Tags", self.tags_edit)
        self.more.setVisible(False)
        root.addWidget(self.more)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        if not self._editing:
            again: QPushButton = self.buttons.addButton(
                "Save && add another", QDialogButtonBox.ButtonRole.ActionRole)
            again.clicked.connect(self._on_save_again)
        self.buttons.accepted.connect(self._on_accept)
        self.buttons.rejected.connect(self.reject)
        style_button_box(self.buttons)
        root.addWidget(self.buttons)

        self.form.setRowVisible(self.budget_label, False)
        if self._budget_hint is not None:
            self.amount_spin.valueChanged.connect(lambda _v: self._update_budget_hint())
            self.category_combo.currentIndexChanged.connect(lambda _i: self._update_budget_hint())
            self.account_combo.currentIndexChanged.connect(lambda _i: self._update_budget_hint())
            self.date_edit.dateChanged.connect(lambda _d: self._update_budget_hint())

    def _toggle_more(self) -> None:
        self.more.setVisible(not self.more.isVisible())
        self.more_btn.setText("Fewer options" if self.more.isVisible() else "More options")
        self.adjustSize()

    # ------------------------------------------------------------ helpers
    def _current_type(self) -> str:
        if self._is_adjustment:
            return "adjustment"
        t = self.type_seg.current() or "expense"
        if t == "investment":
            return self.invest_seg.current() or "investment_buy"
        return t

    def _set_row_visible(self, widget: QWidget, visible: bool) -> None:
        self.form.setRowVisible(widget, visible)

    def _populate_categories(self, t: str) -> None:
        current = self.category_combo.currentData()
        self.category_combo.clear()
        self.category_combo.addItem("Uncategorised", None)
        source = (self._income_categories if t == "income"
                  else self._expense_categories if t == "expense" else [])
        for cid, name in source:
            self.category_combo.addItem(name, cid)
        idx = self.category_combo.findData(current)
        self.category_combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _on_type_changed(self) -> None:
        t = self._current_type()
        self.invest_seg.setVisible(t in ("investment_buy", "investment_sell"))
        self.account_label.setText(_ACCOUNT_LABEL.get(t, "Account"))
        self._set_row_visible(self.counter_combo, t == "transfer")
        self._set_row_visible(self.category_combo, t in ("income", "expense"))
        self._set_row_visible(self.holding_combo, t in ("investment_buy", "investment_sell"))
        self.source_combo.setVisible(t == "income")
        self.source_label.setVisible(t == "income")
        self.desc_edit.setPlaceholderText(_DESC_HINT.get(t, ""))
        self._populate_categories(t)
        self._update_budget_hint()
        self.adjustSize()

    def _update_budget_hint(self) -> None:
        """What's left of the category's budget, before or after this amount."""
        result = None
        category_id = self.category_combo.currentData()
        if (self._budget_hint is not None and category_id is not None
                and self._current_type() == "expense"):
            try:
                result = self._budget_hint(
                    category_id, self.date_edit.date().toString("yyyy-MM-dd"),
                    self.account_combo.currentData(), float(self.amount_spin.value()))
            except Exception:                    # a hint must never block saving
                log.exception("Budget hint failed")
                result = None
        shown = self.budget_label.isVisibleTo(self)
        if result:
            text, tone = result
            self.budget_label.setText(text)
            set_tone(self.budget_label, tone)
        self.form.setRowVisible(self.budget_label, bool(result))
        if shown != bool(result):
            self.adjustSize()

    # --------------------------------------------------------------- values
    def _load(self) -> None:
        t = self._txn
        txn_type = t.txn_type if self._editing else self._default_type
        if txn_type in ("investment_buy", "investment_sell"):
            self.type_seg.set_current("investment")
            self.invest_seg.set_current(txn_type)
        elif txn_type in ("expense", "income", "transfer"):
            self.type_seg.set_current(txn_type)
        self._on_type_changed()

        when = t.txn_date if self._editing else self._default_date
        if when:
            d = QDate.fromString(when[:10], "yyyy-MM-dd")
            if d.isValid():
                self.date_edit.setDate(d)
        self.amount_spin.setValue(float(t.amount or 0.0))
        account_id = t.account_id if self._editing else self._default_account_id
        aidx = self.account_combo.findData(account_id)
        if aidx >= 0:
            self.account_combo.setCurrentIndex(aidx)
        cidx = self.counter_combo.findData(t.counter_account_id)
        self.counter_combo.setCurrentIndex(cidx if cidx >= 0 else 0)
        catidx = self.category_combo.findData(t.category_id)
        self.category_combo.setCurrentIndex(catidx if catidx >= 0 else 0)
        hidx = self.holding_combo.findData(t.holding_id)
        self.holding_combo.setCurrentIndex(hidx if hidx >= 0 else 0)
        sidx = self.source_combo.findData(t.income_source_id)
        self.source_combo.setCurrentIndex(sidx if sidx >= 0 else 0)
        self.desc_edit.setText(t.description or "")
        self.ref_edit.setText(t.reference_no or "")
        self.tags_edit.setText(t.tags or "")
        if t.reference_no or t.tags or t.income_source_id:
            self._toggle_more()
        self.amount_spin.setFocus()
        self.amount_spin.selectAll()

    def _validate(self) -> bool:
        t = self._current_type()
        amount = self.amount_spin.value()
        if t == "adjustment":
            if abs(amount) < 0.005:
                return self._warn("An adjustment must change the balance.", self.amount_spin)
        elif amount <= 0:
            return self._warn("Enter an amount greater than zero.", self.amount_spin)
        if self.account_combo.currentData() is None:
            return self._warn("Choose an account. Add one on the Accounts page first.",
                              self.account_combo)
        if t == "transfer":
            counter = self.counter_combo.currentData()
            if counter is None:
                return self._warn("Choose the account the money went to.", self.counter_combo)
            if counter == self.account_combo.currentData():
                return self._warn("A transfer needs two different accounts.", self.counter_combo)
        return True

    def _warn(self, text: str, widget: QWidget) -> bool:
        QMessageBox.warning(self, "Please check", text)
        widget.setFocus()
        return False

    def _on_accept(self) -> None:
        if self._validate():
            self.accept()

    def _on_save_again(self) -> None:
        if self._validate():
            self.add_another = True
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
        t.category_id = (
            self.category_combo.currentData() if t.txn_type in ("income", "expense") else None
        )
        t.holding_id = (
            self.holding_combo.currentData()
            if t.txn_type in ("investment_buy", "investment_sell") else None
        )
        t.income_source_id = (
            self.source_combo.currentData() if t.txn_type == "income" else None
        )
        t.description = self.desc_edit.text().strip() or None
        t.reference_no = self.ref_edit.text().strip() or None
        t.tags = self.tags_edit.text().strip() or None
        return t
