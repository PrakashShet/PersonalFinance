"""Transactions - ledger with filters, search and monthly summary."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.app_context import AppContext
from ui.dialogs.transaction_dialog import TransactionDialog
from ui.helpers.account_combo import reload_account_combo
from ui.widgets.kpi_card import KpiCard
from utils.formatters import fmt_inr

_TYPE_LABELS = {
    "income": "Income",
    "expense": "Expense",
    "transfer": "Transfer",
    "investment_buy": "Investment Buy",
    "investment_sell": "Investment Sell",
}
_MONTHS = [
    ("01", "January"), ("02", "February"), ("03", "March"), ("04", "April"),
    ("05", "May"), ("06", "June"), ("07", "July"), ("08", "August"),
    ("09", "September"), ("10", "October"), ("11", "November"), ("12", "December"),
]
_COLUMNS = ["Date", "Type", "Account", "Category", "Description", "Amount"]
_POS = QColor("#8fbf8f")
_NEG = QColor("#d88a8a")


class TransactionsView(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.service = ctx.transaction_service
        self._topics = {"transactions", "accounts", "income_sources", "categories"}
        self._dirty = True
        self._rows: list = []

        self.ctx.events.changed.connect(self._on_data_changed)
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QVBoxLayout(self)

        title = QLabel("Transactions")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        # KPI strip
        grid = QGridLayout()
        self.kpi_income = KpiCard("Income", "-")
        self.kpi_expense = KpiCard("Expenses", "-")
        self.kpi_invested = KpiCard("Investments", "-")
        self.kpi_net = KpiCard("Net", "-")
        for i, w in enumerate(
            [self.kpi_income, self.kpi_expense, self.kpi_invested, self.kpi_net]
        ):
            grid.addWidget(w, 0, i)
        root.addLayout(grid)

        # Filter bar
        bar = QHBoxLayout()
        self.month_combo = QComboBox()
        self.month_combo.addItem("All months", None)
        for value, label in _MONTHS:
            self.month_combo.addItem(label, value)

        self.year_combo = QComboBox()
        self.year_combo.addItem("All years", None)
        for y in self.service.years():
            self.year_combo.addItem(y, y)

        self.type_combo = QComboBox()
        self.type_combo.addItem("All types", None)
        for value, label in _TYPE_LABELS.items():
            self.type_combo.addItem(label, value)

        self.account_combo = QComboBox()
        self._accounts: list[tuple] = []

        self.category_combo = QComboBox()
        self.category_combo.addItem("All categories", None)
        for cid, name, kind in self.ctx.category_service.list_all_labeled():
            self.category_combo.addItem(f"{name}  ({kind})", cid)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search description / reference / tags")
        self.search_edit.setClearButtonEnabled(True)

        for w in (self.month_combo, self.year_combo, self.type_combo,
                  self.account_combo, self.category_combo):
            w.currentIndexChanged.connect(self.refresh)
        self.search_edit.textChanged.connect(self.refresh)

        bar.addWidget(self.month_combo)
        bar.addWidget(self.year_combo)
        bar.addWidget(self.type_combo)
        bar.addWidget(self.account_combo)
        bar.addWidget(self.category_combo)
        bar.addWidget(self.search_edit, 1)
        root.addLayout(bar)

        # Action bar
        actions = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.edit_btn = QPushButton("Edit")
        self.delete_btn = QPushButton("Delete")
        self.add_btn.clicked.connect(self._on_add)
        self.edit_btn.clicked.connect(self._on_edit)
        self.delete_btn.clicked.connect(self._on_delete)
        actions.addWidget(self.add_btn)
        actions.addWidget(self.edit_btn)
        actions.addWidget(self.delete_btn)
        actions.addStretch(1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("tileFlags")
        actions.addWidget(self.count_label)
        root.addLayout(actions)

        # Table
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        for c in range(len(_COLUMNS)):
            mode = (
                QHeaderView.ResizeMode.Stretch if c == 4
                else QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(c, mode)
        self.table.doubleClicked.connect(self._on_edit)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        root.addWidget(self.table, 1)

        self._update_buttons()

    # --------------------------------------------------------------- filters
    def _filters(self) -> dict:
        return {
            "year": self.year_combo.currentData(),
            "month": self.month_combo.currentData(),
            "txn_type": self.type_combo.currentData(),
            "account_id": self.account_combo.currentData(),
            "category_id": self.category_combo.currentData(),
            "search": self.search_edit.text().strip() or None,
        }

    # ---------------------------------------------------------------- helpers
    def _selected_id(self) -> Optional[int]:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        r = rows[0].row()
        if 0 <= r < len(self._rows):
            return self._rows[r]["id"]
        return None

    def _update_buttons(self) -> None:
        has = self._selected_id() is not None
        self.edit_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)

    def _category_lists(self):
        return self.ctx.income_categories(), self.ctx.expense_categories()

    def _reload_accounts(self) -> None:
        """Refresh account list and filter dropdown (e.g. after adding an account)."""
        self._accounts = self.ctx.account_options_active()
        reload_account_combo(self.account_combo, self._accounts)

    def _on_data_changed(self, topic: str) -> None:
        if topic in self._topics:
            self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty:
            self.refresh()

    # ---------------------------------------------------------------- actions
    def _on_add(self) -> None:
        self._reload_accounts()
        if not self._accounts:
            QMessageBox.information(
                self, "No accounts", "Create an account first on the Accounts tab."
            )
            return
        income, expense = self._category_lists()
        dialog = TransactionDialog(
            self._accounts,
            income,
            expense,
            self.ctx.income_source_options(),
            parent=self,
        )
        if dialog.exec():
            self.service.create_transaction(dialog.get_transaction())
            self.refresh()

    def _on_edit(self) -> None:
        txn_id = self._selected_id()
        if txn_id is None:
            return
        txn = self.service.get_transaction(txn_id)
        if txn is None:
            return
        self._reload_accounts()
        income, expense = self._category_lists()
        dialog = TransactionDialog(
            self._accounts,
            income,
            expense,
            self.ctx.income_source_options(),
            txn=txn,
            parent=self,
        )
        if dialog.exec():
            self.service.update_transaction(dialog.get_transaction())
            self.refresh()

    def _on_delete(self) -> None:
        txn_id = self._selected_id()
        if txn_id is None:
            return
        confirm = QMessageBox.question(
            self,
            "Delete transaction",
            "Delete this transaction? The linked account balance will be adjusted back.",
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.service.delete_transaction(txn_id)
            self.refresh()

    # ----------------------------------------------------------------- render
    def refresh(self) -> None:
        self._reload_accounts()
        f = self._filters()
        self._rows = self.service.list(**f)

        self.table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            ttype = row["txn_type"]
            self._set(r, 0, row["txn_date"])
            self._set(r, 1, _TYPE_LABELS.get(ttype, ttype))

            account_text = row["account_name"] or "-"
            if ttype == "transfer" and row["counter_account_name"]:
                account_text = f"{account_text}  ->  {row['counter_account_name']}"
            self._set(r, 2, account_text)
            self._set(r, 3, row["category_name"] or "-")
            self._set(r, 4, row["description"] or "-")

            signed = self.service.signed_amount(ttype, row["amount"])
            sign = "+" if signed >= 0 else "-"
            item = QTableWidgetItem(f"{sign}{fmt_inr(abs(signed))}")
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            item.setForeground(_POS if signed >= 0 else _NEG)
            self.table.setItem(r, 5, item)

        self.count_label.setText(f"{len(self._rows)} transaction(s)")
        self._update_kpis(f)
        self._update_buttons()
        self._dirty = False

    def _update_kpis(self, f: dict) -> None:
        s = self.service.summary(year=f["year"], month=f["month"])
        self.kpi_income.set_value(fmt_inr(s["income"], compact=True))
        self.kpi_expense.set_value(fmt_inr(s["expense"], compact=True))
        self.kpi_invested.set_value(fmt_inr(s["invested"], compact=True))
        self.kpi_net.set_value(fmt_inr(s["net"], compact=True))

    def _set(self, row: int, col: int, text: str) -> None:
        self.table.setItem(row, col, QTableWidgetItem(str(text)))
