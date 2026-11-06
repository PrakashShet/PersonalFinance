"""Transactions - the ledger: search, filter by period / type / account,
add / edit / duplicate / delete, with period totals on top."""
from __future__ import annotations

import calendar
from datetime import date
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.transaction import Transaction
from services.app_context import AppContext
from ui.dialogs.transaction_dialog import TransactionDialog
from ui.helpers.account_combo import reload_account_combo
from ui.helpers.budget_text import impact_hint
from ui.theme import icons, theme
from ui.theme.badges import TXN_TYPE_LABELS
from ui.widgets.common import EmptyState, PageHeader, button, label
from ui.widgets.kpi_card import KpiCard
from ui.widgets.toast import notify
from utils.formatters import fmt_date, fmt_inr, fmt_money

_COLUMNS = ["Date", "Description", "Category", "Account", "Type", "Amount"]


def _period_options(today: date) -> list[tuple[str, Optional[tuple[str, str]]]]:
    def month_range(y: int, m: int) -> tuple[str, str]:
        return (date(y, m, 1).isoformat(), date(y, m, calendar.monthrange(y, m)[1]).isoformat())

    prev_y, prev_m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    three_back = today.year * 12 + today.month - 1 - 2
    return [
        ("This month", month_range(today.year, today.month)),
        ("Last month", month_range(prev_y, prev_m)),
        ("Last 3 months", (date(three_back // 12, three_back % 12 + 1, 1).isoformat(), today.isoformat())),
        ("This year", (date(today.year, 1, 1).isoformat(), date(today.year, 12, 31).isoformat())),
        ("Last year", (date(today.year - 1, 1, 1).isoformat(), date(today.year - 1, 12, 31).isoformat())),
        ("All time", None),
    ]


class TransactionsView(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.service = ctx.transaction_service
        self._topics = {"transactions", "accounts", "income_sources", "categories", "holdings"}
        self._dirty = True
        self._rows: list = []
        self._accounts: list[tuple] = []
        self.ctx.events.changed.connect(self._on_data_changed)
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)

        self.add_btn = button("Add transaction", "primary", "plus",
                              on_click=lambda: self.open_add("expense"),
                              tooltip="Ctrl+N")
        root.addWidget(PageHeader(
            "Transactions", "Everything that moved money in or out of your accounts.",
            [self.add_btn]))

        kpis = QHBoxLayout()
        kpis.setSpacing(14)
        self.kpi_income = KpiCard("Income", icon_name="arrow_down_left")
        self.kpi_expense = KpiCard("Spent", icon_name="arrow_up_right")
        self.kpi_invested = KpiCard("Invested", icon_name="investments")
        self.kpi_net = KpiCard("Saved", icon_name="coins")
        for k in (self.kpi_income, self.kpi_expense, self.kpi_invested, self.kpi_net):
            kpis.addWidget(k)
        root.addLayout(kpis)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.period_combo = QComboBox()
        for text, rng in _period_options(date.today()):
            self.period_combo.addItem(text, rng)
        self.type_combo = QComboBox()
        self.type_combo.addItem("All types", None)
        for value, text in TXN_TYPE_LABELS.items():
            self.type_combo.addItem(text, value)
        self.account_combo = QComboBox()
        self.category_combo = QComboBox()
        self._reload_categories()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search notes, categories, accounts")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.addAction(icons.icon("search", theme.color("text_muted"), size=16),
                                   QLineEdit.ActionPosition.LeadingPosition)
        for w in (self.period_combo, self.type_combo, self.account_combo, self.category_combo):
            w.currentIndexChanged.connect(self.refresh)
            bar.addWidget(w)
        self.search_edit.textChanged.connect(self.refresh)
        bar.addWidget(self.search_edit, 1)
        root.addLayout(bar)

        card = QFrame()
        card.setObjectName("card")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(1, 1, 1, 1)
        self.body = QStackedWidget()
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        amount_head = QTableWidgetItem("Amount")
        amount_head.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.table.setHorizontalHeaderItem(len(_COLUMNS) - 1, amount_head)
        self._fit_columns()
        self.table.doubleClicked.connect(lambda _i: self._on_edit())
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.body.addWidget(self.table)
        self.empty = EmptyState("transactions", "No transactions here",
                                "Nothing matches this period and these filters.",
                                "Add transaction", lambda: self.open_add("expense"))
        self.body.addWidget(self.empty)
        card_lay.addWidget(self.body)
        root.addWidget(card, 1)

        foot = QHBoxLayout()
        self.count_label = label("", "small")
        foot.addWidget(self.count_label)
        foot.addStretch(1)
        self.edit_btn = button("Edit", "secondary", "edit", on_click=self._on_edit, size="small")
        self.dup_btn = button("Duplicate", "secondary", on_click=self._on_duplicate, size="small")
        self.delete_btn = button("Delete", "danger", "trash", on_click=self._on_delete, size="small")
        for b in (self.edit_btn, self.dup_btn, self.delete_btn):
            foot.addWidget(b)
        root.addLayout(foot)
        self.table.itemSelectionChanged.connect(self._update_buttons)

        QShortcut(QKeySequence(QKeySequence.StandardKey.Delete), self.table, activated=self._on_delete)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self.table, activated=self._on_edit)
        self._update_buttons()

    # ------------------------------------------------------------- filters
    def _filters(self) -> dict:
        rng = self.period_combo.currentData()
        return {
            "date_from": rng[0] if rng else None,
            "date_to": rng[1] if rng else None,
            "txn_type": self.type_combo.currentData(),
            "account_id": self.account_combo.currentData(),
            "category_id": self.category_combo.currentData(),
            "search": self.search_edit.text().strip() or None,
        }

    def show_with(self, account_id: Optional[int] = None, period: Optional[str] = None,
                  add: Optional[str] = None, category_id: Optional[int] = None,
                  txn_type: Optional[str] = None, date_from: Optional[str] = None,
                  date_to: Optional[str] = None, period_label: Optional[str] = None,
                  **_kw) -> None:
        """Open pre-filtered, or straight into the add dialog (navigation).

        ``date_from``/``date_to`` select a matching period, or add one named
        ``period_label`` (e.g. a budget's "FY 2026–27")."""
        if add:
            self.open_add(add)
            return
        self._reload_accounts()
        self._reload_categories()
        combos = (self.period_combo, self.type_combo, self.account_combo, self.category_combo)
        for combo in combos:
            combo.blockSignals(True)
        try:
            if account_id is not None:
                idx = self.account_combo.findData(account_id)
                if idx >= 0:
                    self.account_combo.setCurrentIndex(idx)
                self.period_combo.setCurrentIndex(self.period_combo.findText("All time"))
            if category_id is not None:
                idx = self.category_combo.findData(category_id)
                if idx >= 0:
                    self.category_combo.setCurrentIndex(idx)
                if account_id is None:
                    self.account_combo.setCurrentIndex(0)        # all accounts
                self.search_edit.blockSignals(True)
                self.search_edit.clear()
                self.search_edit.blockSignals(False)
            if txn_type is not None:
                idx = self.type_combo.findData(txn_type)
                if idx >= 0:
                    self.type_combo.setCurrentIndex(idx)
            if period:
                idx = self.period_combo.findText(period)
                if idx >= 0:
                    self.period_combo.setCurrentIndex(idx)
            if date_from and date_to:
                self._select_range((date_from, date_to), period_label or f"{date_from} – {date_to}")
        finally:
            for combo in combos:
                combo.blockSignals(False)
        self.refresh()

    def _select_range(self, rng: tuple[str, str], text: str) -> None:
        for i in range(self.period_combo.count()):
            if self.period_combo.itemData(i) == rng:
                self.period_combo.setCurrentIndex(i)
                return
        self.period_combo.addItem(text, rng)
        self.period_combo.setCurrentIndex(self.period_combo.count() - 1)

    def _reload_accounts(self) -> None:
        self._accounts = self.ctx.account_options_active()
        everything = sorted(self.ctx.account_name_map().items(), key=lambda kv: kv[1].lower())
        reload_account_combo(self.account_combo, everything)

    def _reload_categories(self) -> None:
        selected = self.category_combo.currentData()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("All categories", None)
        for cid, name, kind in self.ctx.category_service.list_all_labeled():
            self.category_combo.addItem(name, cid)
        idx = self.category_combo.findData(selected)
        self.category_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.category_combo.blockSignals(False)

    # ------------------------------------------------------------- helpers
    def _selected_id(self) -> Optional[int]:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        r = rows[0].row()
        return self._rows[r]["id"] if 0 <= r < len(self._rows) else None

    def _update_buttons(self) -> None:
        has = self._selected_id() is not None
        for b in (self.edit_btn, self.dup_btn, self.delete_btn):
            b.setEnabled(has)

    def _on_data_changed(self, topic: str) -> None:
        if topic in self._topics:
            self._dirty = True

    def mark_dirty(self) -> None:
        self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty:
            self.refresh()

    def _context_menu(self, pos) -> None:
        if self._selected_id() is None:
            return
        menu = QMenu(self)
        for text, fn in (("Edit", self._on_edit), ("Duplicate", self._on_duplicate)):
            act = QAction(text, menu)
            act.triggered.connect(fn)
            menu.addAction(act)
        menu.addSeparator()
        delete = QAction("Delete", menu)
        delete.triggered.connect(self._on_delete)
        menu.addAction(delete)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # ---------------------------------------------------------------- actions
    def _dialog(self, txn: Optional[Transaction] = None, txn_type: str = "expense",
                account_id: Optional[int] = None, when: Optional[str] = None) -> TransactionDialog:
        return TransactionDialog(
            self._accounts, self.ctx.income_categories(), self.ctx.expense_categories(),
            self.ctx.income_source_options(), txn=txn, parent=self,
            holdings=self.ctx.holding_options(), default_type=txn_type,
            default_account_id=account_id or self.ctx.preferences.get("last_account_id"),
            default_date=when,
            budget_hint=self._budget_hint(txn.id if txn is not None else None),
        )

    def _budget_hint(self, editing_id: Optional[int]):
        """Lookup for the dialog's budget line. The entry being edited is left
        out of what's already spent, so it isn't counted twice."""
        currencies = self.ctx.account_currencies()
        svc = self.ctx.budget_service

        def hint(category_id: int, when: str, account_id: Optional[int], amount: float):
            return impact_hint(svc.impact(category_id, when, amount,
                                          currencies.get(account_id, "INR"),
                                          exclude_txn_id=editing_id))
        return hint

    def open_add(self, txn_type: str = "expense") -> None:
        self._reload_accounts()
        if not self._accounts:
            QMessageBox.information(self, "Add an account first",
                                    "Transactions belong to an account. Add one on the Accounts page.")
            return
        account_id, when = None, None
        while True:
            dlg = self._dialog(txn_type=txn_type, account_id=account_id, when=when)
            if not dlg.exec():
                break
            txn = dlg.get_transaction()
            try:
                self.service.create_transaction(txn)
            except ValueError as e:
                QMessageBox.warning(self, "Couldn't save", str(e))
                break
            self.ctx.preferences.set("last_account_id", txn.account_id)
            notify("Transaction added")
            if not dlg.add_another:
                break
            txn_type = txn.txn_type if txn.txn_type in ("expense", "income", "transfer") else "investment_buy"
            account_id, when = txn.account_id, txn.txn_date
        self.refresh()

    def _on_edit(self) -> None:
        txn_id = self._selected_id()
        txn = self.service.get_transaction(txn_id) if txn_id is not None else None
        if txn is None:
            return
        self._reload_accounts()
        dlg = self._dialog(txn=txn)
        if dlg.exec():
            try:
                self.service.update_transaction(dlg.get_transaction())
            except ValueError as e:
                QMessageBox.warning(self, "Couldn't save", str(e))
                return
            self.refresh()
            notify("Saved")

    def _on_duplicate(self) -> None:
        txn_id = self._selected_id()
        txn = self.service.get_transaction(txn_id) if txn_id is not None else None
        if txn is None or txn.txn_type == "adjustment":
            return
        copy = Transaction(**{**txn.to_dict(), "id": None, "created_at": None,
                              "txn_date": date.today().isoformat(), "tags": None})
        self._reload_accounts()
        dlg = self._dialog(txn=copy)
        dlg.setWindowTitle("Duplicate transaction")
        if dlg.exec():
            new = dlg.get_transaction()
            new.id = None
            self.service.create_transaction(new)
            self.refresh()
            notify("Transaction added")

    def _on_delete(self) -> None:
        txn_id = self._selected_id()
        if txn_id is None:
            return
        confirm = QMessageBox.question(
            self, "Delete transaction",
            "Delete this transaction? The account balance is adjusted back.")
        if confirm == QMessageBox.StandardButton.Yes:
            self.service.delete_transaction(txn_id)
            self.refresh()
            notify("Deleted")

    # ----------------------------------------------------------------- render
    def refresh(self) -> None:
        self._reload_accounts()
        self._reload_categories()
        f = self._filters()
        self._rows = self.service.list(**f)
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        positive = theme.qcolor("positive")
        muted = theme.qcolor("text_muted")

        # Fill without repainting or re-fitting columns after every cell: with
        # "resize to contents" on, that work grows with rows x rows (minutes for
        # a few years of history after a theme change). Fit once at the end.
        header = self.table.horizontalHeader()
        self.table.setUpdatesEnabled(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        try:
            self._fill(f, right, positive, muted)
        finally:
            self._fit_columns()
            self.table.setUpdatesEnabled(True)

        self.body.setCurrentIndex(0 if self._rows else 1)
        n = len(self._rows)
        self.count_label.setText(f"{n} transaction{'s' if n != 1 else ''}")
        self._update_kpis(f)
        self._update_buttons()
        self._dirty = False

    def _fit_columns(self) -> None:
        header = self.table.horizontalHeader()
        for c in range(len(_COLUMNS)):
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

    def _fill(self, f: dict, right, positive, muted) -> None:
        self.table.setRowCount(len(self._rows))
        for r, row in enumerate(self._rows):
            ttype = row["txn_type"]
            self._set(r, 0, fmt_date(row["txn_date"], "%d %b %Y"))
            desc = row["description"] or row["category_name"] or TXN_TYPE_LABELS.get(ttype, ttype)
            self._set(r, 1, desc)
            self._set(r, 2, row["category_name"] or "-")
            account_text = row["account_name"] or "-"
            if ttype == "transfer" and row["counter_account_name"]:
                account_text = f"{account_text}  →  {row['counter_account_name']}"
            self._set(r, 3, account_text)
            type_item = self._set(r, 4, TXN_TYPE_LABELS.get(ttype, ttype))
            type_item.setForeground(muted)

            signed = self.service.signed_amount(ttype, row["amount"])
            if ttype == "transfer" and f["account_id"] and row["counter_account_id"] == f["account_id"]:
                signed = abs(row["amount"])
            text = ("+" if signed > 0 else "−") + fmt_money(abs(signed), row["account_currency"] or "INR")
            item = QTableWidgetItem(text)
            item.setTextAlignment(right)
            if signed > 0:
                item.setForeground(positive)
            self.table.setItem(r, 5, item)

    def _update_kpis(self, f: dict) -> None:
        s = self.service.summary(date_from=f["date_from"], date_to=f["date_to"])
        self.kpi_income.set_value(fmt_inr(s["income"], compact=True))
        self.kpi_expense.set_value(fmt_inr(s["expense"], compact=True))
        self.kpi_invested.set_value(fmt_inr(s["invested"], compact=True))
        net = s["net"]
        self.kpi_net.set_value(("" if net >= 0 else "−") + fmt_inr(abs(net), compact=True),
                               "positive" if net > 0 else ("negative" if net < 0 else None))
        if s["income"] > 0:
            self.kpi_net.set_hint(f"{net / s['income'] * 100:.0f}% of income")
        else:
            self.kpi_net.set_hint("")

    def _set(self, row: int, col: int, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(str(text))
        self.table.setItem(row, col, item)
        return item

