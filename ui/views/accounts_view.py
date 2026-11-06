"""Accounts - bank accounts, cash and wallets.

Balances move through the ledger: "Update balance" records the difference as
an adjustment, so editing never silently rewrites history.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QMenu, QMessageBox, QVBoxLayout, QWidget

from config.account_fields import ACCOUNT_SECTION, SECTIONS, Field, label_for_value
from models.account import Account
from ui import navigation
from ui.dialogs.quick_dialogs import UpdateBalanceDialog
from ui.dialogs.section_edit_dialog import SectionEditDialog
from ui.theme.badges import ACCOUNT_TYPE_LABELS, label as type_label
from ui.views.master_detail import MasterDetailView
from ui.widgets.common import ActivityRow, button, escape_mnemonic, label
from ui.widgets.detail_panel import DetailPanel
from ui.widgets.kpi_card import KpiCard
from ui.widgets.list_tile import ListTile
from ui.widgets.toast import notify
from utils.formatters import fmt_date, fmt_inr, fmt_money

_TYPE_ICON = {
    "savings": "accounts", "current": "accounts", "salary": "accounts",
    "cash": "wallet", "wallet": "wallet", "credit_card": "liabilities",
}


class AccountsView(MasterDetailView):
    title = "Accounts"
    subtitle = "Bank accounts, cash and wallets. Balances follow your transactions."
    add_label = "Add account"
    topics = frozenset({"accounts", "transactions", "liabilities", "fx_rates"})
    inactive_label = "Show archived"
    empty_icon = "accounts"
    empty_title = "No accounts yet"
    empty_text = "Add your bank accounts, cash and wallets to start tracking."
    select_hint = "Select an account to see its balance, details and recent activity."

    def __init__(self, ctx) -> None:
        self._mismatch: dict = {}
        super().__init__(ctx)

    # ------------------------------------------------------------- hooks
    def build_kpis(self):
        self.k_cash = KpiCard("Cash & bank", icon_name="wallet")
        self.k_count = KpiCard("Active accounts", icon_name="accounts")
        self.k_cc = KpiCard("Credit cards owed", icon_name="liabilities")
        return [self.k_cash, self.k_count, self.k_cc]

    def fetch(self, include_inactive: bool):
        svc = self.ctx.account_service
        self._mismatch = {m.account.id: m for m in svc.reconciliation_report()}
        return svc.get_all(include_archived=include_inactive)

    def refresh_kpis(self, items) -> None:
        s = self.ctx.account_service.account_summary()
        self.k_cash.set_value(fmt_inr(s["liquid_balance"], compact=True))
        missing = s.get("unconverted") or {}
        self.k_cash.set_hint(
            ("Not counted: " + ", ".join(f"{fmt_money(v, k)}" for k, v in missing.items())
             + " - add a rate in Settings") if missing else "Excludes credit cards",
            "warning" if missing else None)
        self.k_count.set_value(str(s["count"]))
        self.k_cc.set_value(fmt_inr(abs(s["credit_card_outstanding"]), compact=True))

    def make_tile(self, a: Account, selected: bool) -> ListTile:
        meta = " · ".join(x for x in [type_label(ACCOUNT_TYPE_LABELS, a.account_type),
                                      a.institution] if x)
        return ListTile(
            a.id, a.name, meta,
            value=fmt_money(a.current_balance, a.currency),
            badge=("Archived", "neutral") if a.is_active != 1 else None,
            chip=("Check balance", "warning") if a.id in self._mismatch else None,
            icon_name=_TYPE_ICON.get(a.account_type, "accounts"),
            muted=a.is_active != 1, selected=selected,
        )

    def on_add(self) -> None:
        dialog = SectionEditDialog(Account(), ACCOUNT_SECTION, parent=self,
                                   title="Add account", creating=True)
        if dialog.exec():
            account = dialog.get_account()
            try:
                new_id = self.ctx.account_service.create_account(account)
            except ValueError as e:
                QMessageBox.warning(self, "Couldn't add account", str(e))
                return
            self._selected_id = new_id
            self.refresh()
            notify(f"Added {account.name}")

    def on_activate(self, a: Account) -> None:
        self._edit_section(ACCOUNT_SECTION)

    # ------------------------------------------------------------ detail
    def render_detail(self, a: Account, panel: DetailPanel) -> None:
        bits = [type_label(ACCOUNT_TYPE_LABELS, a.account_type)]
        if a.institution:
            bits.append(a.institution)
        if a.account_number:
            bits.append(f"•••• {a.account_number[-4:]}")
        badges = [("Archived", "neutral")] if a.is_active != 1 else []
        panel.set_header(a.name, "  ·  ".join(bits), badges)

        actions = []
        if a.is_active == 1:
            actions.append(("Update balance", self._update_balance, "primary", "edit"))
        actions.append(("Edit details", lambda: self._edit_section(ACCOUNT_SECTION), "secondary"))
        if a.is_active == 1:
            actions.append(("Archive", self._toggle_archive, "ghost", "archive"))
        else:
            actions.append(("Restore", self._toggle_archive, "secondary", "restore"))
        panel.set_actions(actions)

        mismatch = self._mismatch.get(a.id)
        if mismatch is not None:
            panel.add_banner(
                f"The balance differs from this account's transactions by "
                f"{fmt_money(mismatch.difference, a.currency)}. Reconciling records the "
                "difference so edits to older entries stay correct.",
                "warning", "Reconcile", self._reconcile)

        if self.ctx.account_has_loan_fields(a):
            linked = self.ctx.liability_service.for_account(a.id)
            if linked is None:
                panel.add_banner(
                    "This account describes a loan that isn't in Liabilities, so it is not "
                    "counted in your net worth.", "info", "Track in Liabilities",
                    self._track_loan)
            else:
                panel.add_banner(f"Loan tracked in Liabilities as “{linked.name}”.",
                                 "positive")

        panel.add_stats("Balance", [
            ("Balance today", fmt_money(a.current_balance, a.currency)),
            ("Opening balance", fmt_money(a.opening_balance, a.currency)),
            ("Currency", a.currency or "INR"),
        ])
        self._render_activity(a, panel)

        empty_sections = []
        for section in SECTIONS[1:]:
            rows = [(f.label, self._fmt(f, getattr(a, f.attr, None)), None)
                    for f in section.fields if self._has_value(f, getattr(a, f.attr, None))]
            if rows:
                panel.add_stats(section.title, rows, columns=2,
                                action=("Edit", lambda s=section: self._edit_section(s)))
            else:
                empty_sections.append(section)
        if empty_sections:
            holder = QWidget()
            col = QVBoxLayout(holder)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(6)
            col.addWidget(label("Add more details", "sectionTitle"))
            col.addWidget(label("Optional - keep KYC, demat, card and loan details in one place.",
                                "muted", wrap=True))
            row = QHBoxLayout()
            add = button("Add details", "secondary", "plus", size="small")
            menu = QMenu(add)
            for s in empty_sections:
                act = menu.addAction(escape_mnemonic(s.title))
                act.triggered.connect(lambda _c=False, s=s: self._edit_section(s))
            add.setMenu(menu)
            row.addWidget(add)
            row.addStretch(1)
            col.addLayout(row)
            panel.add_widget(holder)

    def _render_activity(self, a: Account, panel: DetailPanel) -> None:
        rows = self.ctx.transaction_service.list(account_id=a.id, limit=5)
        holder = QWidget()
        col = QVBoxLayout(holder)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        if not rows:
            col.addWidget(label("No transactions yet.", "muted"))
        for r in rows:
            signed = self.ctx.transaction_service.signed_amount(r["txn_type"], r["amount"])
            if r["txn_type"] == "transfer" and r["counter_account_id"] == a.id:
                signed = abs(r["amount"])
            title = r["description"] or r["category_name"] or r["txn_type"].replace("_", " ").title()
            meta = (r["category_name"] or "") if r["description"] else ""
            col.addWidget(ActivityRow(
                fmt_date(r["txn_date"], "%d %b"), title, meta,
                ("+" if signed > 0 else "−") + fmt_money(abs(signed), a.currency),
                "positive" if signed > 0 else None))
        panel.add_section("Recent activity", holder,
                          action=("View all", lambda: navigation.go("transactions", account_id=a.id)))

    @staticmethod
    def _has_value(f: Field, value) -> bool:
        if f.kind == "checkbox":
            return bool(value)
        if f.kind in ("money", "percent", "int", "day"):
            return bool(value)
        return value not in (None, "")

    @staticmethod
    def _fmt(f: Field, value) -> str:
        if f.kind == "checkbox":
            return "Yes" if value else "No"
        if f.kind == "money":
            return fmt_inr(value or 0.0)
        if f.kind == "percent":
            return f"{value:.2f}%"
        if f.kind == "combo":
            return label_for_value(f, value) or "-"
        return str(value)

    # ----------------------------------------------------------- actions
    def _edit_section(self, section) -> None:
        a = self.selected()
        if a is None:
            return
        dialog = SectionEditDialog(a, section, parent=self)
        if dialog.exec():
            try:
                self.ctx.account_service.update_account(dialog.get_account())
            except ValueError as e:
                QMessageBox.warning(self, "Couldn't save", str(e))
                return
            self.refresh()
            notify("Saved")

    def _update_balance(self) -> None:
        a = self.selected()
        if a is None:
            return
        dialog = UpdateBalanceDialog(a.name, a.current_balance, a.currency, self)
        if dialog.exec():
            delta = self.ctx.account_service.set_balance(a.id, dialog.value())
            self.refresh()
            if abs(delta) >= 0.005:
                notify(f"Balance updated ({'+' if delta > 0 else '−'}{fmt_money(abs(delta), a.currency)})")

    def _reconcile(self) -> None:
        a = self.selected()
        if a is None:
            return
        diff = self.ctx.account_service.reconcile(a.id)
        self.refresh()
        notify(f"Reconciled {a.name} ({fmt_money(diff, a.currency)})")

    def _track_loan(self) -> None:
        a = self.selected()
        if a is None:
            return
        self.ctx.liability_service.create_from_account_loan(a)
        self.refresh()
        notify("Loan added to Liabilities")

    def _toggle_archive(self) -> None:
        a = self.selected()
        if a is None:
            return
        svc = self.ctx.account_service
        if a.is_active == 1:
            ok = QMessageBox.question(
                self, "Archive account",
                f"Archive “{a.name}”?\n\nIt disappears from lists and totals; its "
                "history is kept and you can restore it any time (Show archived).")
            if ok != QMessageBox.StandardButton.Yes:
                return
            svc.archive_account(a.id)
            notify(f"Archived {a.name}")
        else:
            svc.restore_account(a.id)
            notify(f"Restored {a.name}")
        self.refresh()
