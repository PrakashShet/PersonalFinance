"""Income - where money comes from, and what actually arrived each month.

Recording a month can post the income into its account in the same step, so
balances stay in sync (IncomeService).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from models.income import IncomeSource
from services.income_service import IncomeService
from ui.dialogs.income_dialog import IncomeDialog
from ui.dialogs.record_income_dialog import RecordIncomeDialog
from ui.theme import theme
from ui.theme.badges import FREQ_LABELS, INCOME_SOURCE_LABELS, label as type_label
from ui.views.master_detail import MasterDetailView
from ui.widgets.common import button, label
from ui.widgets.detail_panel import DetailPanel
from ui.widgets.kpi_card import KpiCard
from ui.widgets.list_tile import ListTile
from ui.widgets.toast import notify
from utils.formatters import fmt_inr

HISTORY_COLS = ["Month", "Expected", "Received", "Difference", "Account", "In ledger"]


def _month_label(period: str) -> str:
    try:
        return date.fromisoformat(f"{period}-01").strftime("%b %Y")
    except ValueError:
        return period


class IncomeView(MasterDetailView):
    title = "Income"
    subtitle = "Salary and other income. Record each month to keep balances in sync."
    add_label = "Add income source"
    topics = frozenset({"income_sources", "income_entries", "accounts", "transactions"})
    inactive_label = "Show inactive"
    empty_icon = "income"
    empty_title = "No income sources yet"
    empty_text = "Add your salary or other income to track what arrives each month."
    select_hint = "Select an income source to see its breakdown and monthly history."

    def __init__(self, ctx) -> None:
        self._service = ctx.income_source_service
        self.history_table: Optional[QTableWidget] = None
        self._entries: list = []
        super().__init__(ctx)

    def build_kpis(self):
        self.k_net = KpiCard("Expected take-home", icon_name="income")
        self.k_received = KpiCard("Received this month", icon_name="check_circle")
        self.k_gross = KpiCard("Gross per month", icon_name="coins")
        self.k_deduct = KpiCard("Deductions per month", icon_name="scale")
        return [self.k_net, self.k_received, self.k_gross, self.k_deduct]

    def fetch(self, include_inactive: bool):
        return self._service.list_all(include_inactive)

    def refresh_kpis(self, items) -> None:
        active = [s for s in items if s.is_active]
        net = sum(self._service.net_monthly(s) for s in active)
        received = self._service.total_received(date.today().strftime("%Y-%m"))
        self.k_net.set_value(fmt_inr(net, compact=True))
        self.k_net.set_hint(f"{len(active)} source{'s' if len(active) != 1 else ''} per month")
        self.k_received.set_value(fmt_inr(received, compact=True))
        if net > 0:
            self.k_received.set_hint(f"{min(received / net, 9.99) * 100:.0f}% of expected")
        self.k_gross.set_value(fmt_inr(sum(self._service.gross_monthly(s) for s in active), compact=True))
        self.k_deduct.set_value(fmt_inr(sum(self._service.deductions_monthly(s) for s in active), compact=True))

    def _month_status(self, s: IncomeSource) -> Optional[tuple[str, str]]:
        if not s.is_active or not self._service.is_recurring_monthly(s):
            return None
        period = date.today().strftime("%Y-%m")
        if self._service.has_logged(s.id, period):
            return ("Recorded", "positive")
        return ("Not recorded", "warning")

    def make_tile(self, s: IncomeSource, selected: bool) -> ListTile:
        accounts = self.ctx.account_name_map()
        meta = " · ".join(x for x in [
            type_label(INCOME_SOURCE_LABELS, s.source_type),
            FREQ_LABELS.get(s.frequency or "", ""),
            accounts.get(s.deposit_account_id, "")] if x)
        return ListTile(
            s.id, s.name, meta, value=fmt_inr(self._service.net_monthly(s), compact=True) + "/mo",
            badge=("Inactive", "neutral") if not s.is_active else None,
            chip=self._month_status(s), icon_name="income",
            muted=not s.is_active, selected=selected,
        )

    def on_add(self) -> None:
        dlg = IncomeDialog(self, accounts=self.ctx.account_options_active())
        if dlg.exec() == IncomeDialog.DialogCode.Accepted:
            src = dlg.get_source()
            self._selected_id = self._service.create(src)
            self.refresh()
            notify(f"Added {src.name}")

    def on_activate(self, s: IncomeSource) -> None:
        self._edit()

    # ------------------------------------------------------------ detail
    def render_detail(self, s: IncomeSource, panel: DetailPanel) -> None:
        accounts = self.ctx.account_name_map()
        meta = " · ".join(x for x in [type_label(INCOME_SOURCE_LABELS, s.source_type),
                                      FREQ_LABELS.get(s.frequency or "", "")] if x)
        status = self._month_status(s)
        badges = [status] if status else []
        if not s.is_active:
            badges.append(("Inactive", "neutral"))
        panel.set_header(s.name, meta, badges)
        actions = []
        if s.is_active:
            actions.append(("Record this month", self._record, "primary", "check"))
        actions += [("Edit", self._edit, "secondary", "edit"),
                    ("Reactivate" if not s.is_active else "Deactivate", self._toggle, "ghost"),
                    ("Delete", self._delete, "danger", "trash")]
        panel.set_actions(actions)

        rows = [("Take-home per month", fmt_inr(self._service.net_monthly(s)), "positive")]
        if s.employer:
            rows.append(("Employer", s.employer))
        rows.append(("Paid into", accounts.get(s.deposit_account_id, "Not linked")))
        panel.add_stats("Overview", rows)

        if s.source_type == "salary":
            earnings = [("Basic", fmt_inr(s.basic or 0)), ("HRA", fmt_inr(s.hra or 0)),
                        ("Special allowance", fmt_inr(s.special_allow or 0))]
            deductions = [("PF (you)", fmt_inr(s.pf_employee or 0), "negative"),
                          ("PF (employer)", fmt_inr(s.pf_employer or 0)),
                          ("Professional tax", fmt_inr(s.professional_tax or 0), "negative"),
                          ("TDS", fmt_inr(s.tds or 0), "negative")]
            panel.add_stats("Monthly earnings", earnings)
            panel.add_stats("Monthly deductions", deductions, columns=4)
            panel.add_stats("Net", [("Take-home", fmt_inr(IncomeService.net_monthly(s)), "positive")])

        panel.add_section("Monthly history", self._history_widget(s))
        if s.notes:
            panel.add_text(s.notes)

    def _history_widget(self, s: IncomeSource) -> QWidget:
        holder = QWidget()
        col = QVBoxLayout(holder)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)
        self._entries = self._service.list_entries(s.id)
        accounts = self.ctx.account_name_map()

        table = QTableWidget(len(self._entries), len(HISTORY_COLS))
        table.setHorizontalHeaderLabels(HISTORY_COLS)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(36)
        table.setShowGrid(False)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        header = table.horizontalHeader()
        for c in range(len(HISTORY_COLS)):
            header.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for r, e in enumerate(self._entries):
            month = QTableWidgetItem(_month_label(e.period_month))
            month.setData(Qt.ItemDataRole.UserRole, e.id)
            table.setItem(r, 0, month)
            for c, value in ((1, e.expected_amount), (2, e.actual_amount)):
                it = QTableWidgetItem(fmt_inr(value, compact=True) if value else "-")
                it.setTextAlignment(right)
                table.setItem(r, c, it)
            if e.expected_amount:
                delta = (e.actual_amount or 0) - e.expected_amount
                it = QTableWidgetItem(("+" if delta >= 0 else "−") + fmt_inr(abs(delta), compact=True))
                it.setForeground(theme.qcolor("positive" if delta >= 0 else "negative"))
            else:
                it = QTableWidgetItem("-")
            it.setTextAlignment(right)
            table.setItem(r, 3, it)
            table.setItem(r, 4, QTableWidgetItem(accounts.get(e.account_id, "-")))
            posted = QTableWidgetItem("Yes" if e.transaction_id else "No")
            posted.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            table.setItem(r, 5, posted)
        table.setMinimumHeight(min(320, 44 + 36 * max(1, len(self._entries))))
        table.doubleClicked.connect(lambda _i: self._edit_entry())
        self.history_table = table

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.edit_entry_btn = button("Edit month", "secondary", "edit", on_click=self._edit_entry,
                                     size="small")
        self.delete_entry_btn = button("Delete month", "danger", "trash",
                                       on_click=self._delete_entry, size="small")
        for b in (self.edit_entry_btn, self.delete_entry_btn):
            b.setEnabled(False)
            actions.addWidget(b)
        actions.addStretch(1)
        table.itemSelectionChanged.connect(self._on_entry_selection)

        if self._entries:
            col.addWidget(table)
            col.addLayout(actions)
        else:
            col.addWidget(label("Nothing recorded yet. Use “Record this month” when it arrives.",
                                "muted", wrap=True))
        return holder

    def _on_entry_selection(self) -> None:
        has = self._selected_entry() is not None
        self.edit_entry_btn.setEnabled(has)
        self.delete_entry_btn.setEnabled(has)

    def _selected_entry(self):
        if self.history_table is None:
            return None
        rows = self.history_table.selectionModel().selectedRows()
        if not rows:
            return None
        item = self.history_table.item(rows[0].row(), 0)
        eid = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next((e for e in self._entries if e.id == eid), None)

    # ----------------------------------------------------------- actions
    def _record(self) -> None:
        s = self.selected()
        if s is None:
            return
        self.record_for(s)

    def record_for(self, s: IncomeSource) -> bool:
        dlg = RecordIncomeDialog(s, self.ctx.account_options_active(),
                                 expected_net=self._service.net_monthly(s), parent=self)
        if dlg.exec() != RecordIncomeDialog.DialogCode.Accepted:
            return False
        try:
            self._service.record_month(s, **dlg.get_values())
        except ValueError as exc:
            QMessageBox.warning(self, "Couldn't record", str(exc))
            return False
        self.refresh()
        notify(f"Recorded {s.name}")
        return True

    def _edit_entry(self) -> None:
        s = self.selected()
        entry = self._selected_entry()
        if s is None or entry is None:
            return
        dlg = RecordIncomeDialog(s, self.ctx.account_options_active(),
                                 expected_net=self._service.net_monthly(s), entry=entry, parent=self)
        if dlg.exec() != RecordIncomeDialog.DialogCode.Accepted:
            return
        values = dlg.get_values()
        try:
            if values["period_month"] != entry.period_month:
                self._service.delete_entry(entry.id)
            self._service.record_month(s, **values)
        except ValueError as exc:
            QMessageBox.warning(self, "Couldn't save", str(exc))
            return
        self.refresh()
        notify("Saved")

    def _delete_entry(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        ans = QMessageBox.question(
            self, "Delete month",
            f"Delete the {_month_label(entry.period_month)} entry? If it was posted to an "
            "account, that transaction is removed too and the balance adjusted back.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if ans == QMessageBox.StandardButton.Yes:
            self._service.delete_entry(entry.id)
            self.refresh()
            notify("Deleted")

    def _edit(self) -> None:
        s = self.selected()
        if s is None:
            return
        dlg = IncomeDialog(self, s, accounts=self.ctx.account_options_active())
        if dlg.exec() == IncomeDialog.DialogCode.Accepted:
            self._service.update(dlg.get_source())
            self.refresh()
            notify("Saved")

    def _toggle(self) -> None:
        s = self.selected()
        if s is not None:
            self._service.toggle_active(s)
            self.refresh()

    def _delete(self) -> None:
        s = self.selected()
        if s is None:
            return
        ans = QMessageBox.question(
            self, "Delete income source",
            f"Delete “{s.name}” and its monthly history? This can't be undone. "
            "(To keep the history, deactivate it instead.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if ans == QMessageBox.StandardButton.Yes:
            self._service.delete(s.id)
            self._selected_id = None
            self.refresh()
            notify("Deleted")
