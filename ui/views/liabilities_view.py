"""Liabilities - loans, credit card debt and BNPL: what you owe and when."""
from __future__ import annotations

from datetime import date
from typing import Optional

from PyQt6.QtWidgets import QMessageBox

from models.liability import Liability
from services.recurring_service import KIND_EMI, DueItem
from ui.dialogs.liability_dialog import LiabilityDialog
from ui.dialogs.quick_dialogs import LogPaymentDialog
from ui.theme.badges import LIABILITY_LABELS, label as type_label
from ui.views.master_detail import MasterDetailView
from ui.widgets.detail_panel import DetailPanel
from ui.widgets.kpi_card import KpiCard
from ui.widgets.list_tile import ListTile
from ui.widgets.toast import notify
from utils.calculators import emi as calc_emi
from utils.formatters import fmt_date, fmt_inr, fmt_pct


def _months_label(months: Optional[int]) -> str:
    if not months:
        return "-"
    y, m = divmod(int(months), 12)
    return " ".join(p for p in (f"{y} yr" if y else "", f"{m} mo" if m else "") if p)


def _is_overdue(due: Optional[str]) -> bool:
    try:
        return bool(due) and date.fromisoformat(due[:10]) < date.today()
    except ValueError:
        return False


def _emi(lb: Liability) -> float:
    if lb.emi_amount:
        return float(lb.emi_amount)
    if lb.remaining_months and lb.interest_rate:
        return calc_emi(lb.outstanding, lb.interest_rate / 100, lb.remaining_months)
    return 0.0


class LiabilitiesView(MasterDetailView):
    title = "Liabilities"
    subtitle = "Loans, credit card dues and BNPL. These are subtracted from your net worth."
    add_label = "Add liability"
    topics = frozenset({"liabilities", "accounts", "transactions"})
    inactive_label = "Show closed"
    empty_icon = "liabilities"
    empty_title = "No liabilities"
    empty_text = "Debt-free, or not added yet. Add loans and card dues to see what you owe."
    select_hint = "Select a loan to see repayment progress and what's left to pay."

    def build_kpis(self):
        self.k_out = KpiCard("Total owed", icon_name="liabilities")
        self.k_emi = KpiCard("EMIs per month", icon_name="repeat")
        self.k_rate = KpiCard("Average interest", icon_name="scale")
        self.k_free = KpiCard("Debt-free in", icon_name="calendar")
        return [self.k_out, self.k_emi, self.k_rate, self.k_free]

    def fetch(self, include_inactive: bool):
        return self.ctx.liability_service.list_all(include_inactive)

    def refresh_kpis(self, items) -> None:
        active = [lb for lb in items if lb.is_active]
        total = sum(lb.outstanding for lb in active)
        weighted = sum((lb.interest_rate or 0) * lb.outstanding for lb in active)
        self.k_out.set_value(fmt_inr(total, compact=True))
        self.k_out.set_hint(f"{len(active)} active")
        self.k_emi.set_value(fmt_inr(sum(_emi(lb) for lb in active), compact=True))
        self.k_rate.set_value(fmt_pct(weighted / total) if total > 0 else "-")
        longest = max((lb.remaining_months or 0 for lb in active), default=0)
        self.k_free.set_value(_months_label(longest) if longest else ("Now" if not total else "-"))

    def make_tile(self, lb: Liability, selected: bool) -> ListTile:
        meta = " · ".join(x for x in [type_label(LIABILITY_LABELS, lb.liability_type), lb.lender] if x)
        repaid = ((lb.principal - lb.outstanding) / lb.principal * 100) if lb.principal else None
        if _is_overdue(lb.next_due_date) and lb.is_active:
            chip = ("Overdue", "negative")
        elif lb.interest_rate:
            chip = (f"{fmt_pct(lb.interest_rate)} p.a.", "neutral")
        else:
            chip = None
        return ListTile(
            lb.id, lb.name, meta, value=fmt_inr(lb.outstanding),
            badge=("Closed", "neutral") if not lb.is_active else None, chip=chip,
            progress_pct=repaid, progress_tone="positive",
            icon_name="liabilities", muted=not lb.is_active, selected=selected,
        )

    def on_add(self) -> None:
        dlg = LiabilityDialog(self, accounts=self.ctx.account_options_active())
        if dlg.exec() == LiabilityDialog.DialogCode.Accepted:
            lb = dlg.get_liability()
            self._selected_id = self.ctx.liability_service.create(lb)
            self.refresh()
            notify(f"Added {lb.name}")

    def on_activate(self, lb: Liability) -> None:
        self._edit()

    def render_detail(self, lb: Liability, panel: DetailPanel) -> None:
        accounts = self.ctx.account_name_map()
        meta = " · ".join(x for x in [type_label(LIABILITY_LABELS, lb.liability_type), lb.lender] if x)
        badges = []
        if not lb.is_active:
            badges.append(("Closed", "neutral"))
        elif _is_overdue(lb.next_due_date):
            badges.append(("Overdue", "negative"))
        panel.set_header(lb.name, meta, badges)

        emi_val = _emi(lb)
        actions = []
        if lb.is_active and emi_val > 0 and lb.outstanding > 0:
            actions.append(("Log EMI", self._log_emi, "primary", "check"))
        actions += [("Edit", self._edit, "secondary", "edit"),
                    ("Reopen" if not lb.is_active else "Mark closed", self._toggle, "ghost"),
                    ("Delete", self._delete, "danger", "trash")]
        panel.set_actions(actions)

        if _is_overdue(lb.next_due_date) and lb.is_active:
            panel.add_banner(f"Payment was due on {fmt_date(lb.next_due_date)}. Log it once paid.",
                             "negative")

        paid = (lb.principal - lb.outstanding) if lb.principal else 0.0
        rows = [("Outstanding", fmt_inr(lb.outstanding), "negative")]
        if lb.principal:
            rows += [("Borrowed", fmt_inr(lb.principal)),
                     ("Repaid", f"{fmt_inr(paid)} ({paid / lb.principal * 100:.0f}%)", "positive")]
        panel.add_stats("Balance", rows)

        terms = []
        if lb.interest_rate:
            terms.append(("Interest rate", f"{fmt_pct(lb.interest_rate)} a year"))
        if emi_val:
            terms.append(("EMI", f"{fmt_inr(emi_val)} / month"))
        if lb.remaining_months:
            terms.append(("Time left", _months_label(lb.remaining_months)))
            if emi_val:
                interest_left = max(0.0, emi_val * lb.remaining_months - lb.outstanding)
                terms.append(("Interest still to pay", fmt_inr(interest_left), "warning"))
        if lb.next_due_date:
            terms.append(("Next due", fmt_date(lb.next_due_date)))
        if lb.account_id:
            terms.append(("Paid from", accounts.get(lb.account_id, "-")))
        if lb.start_date:
            terms.append(("Started", fmt_date(lb.start_date)))
        if terms:
            panel.add_stats("Repayment", terms)
        if lb.notes:
            panel.add_text(lb.notes)

    # ----------------------------------------------------------- actions
    def _log_emi(self) -> None:
        lb = self.selected()
        if lb is None:
            return
        due = lb.next_due_date or date.today().isoformat()
        item = DueItem(key=f"emi:{lb.id}:{due[:7]}", kind=KIND_EMI, title=f"EMI - {lb.name}",
                       due_date=due, amount=_emi(lb), account_id=lb.account_id, ref_id=lb.id,
                       action="log")
        dlg = LogPaymentDialog(f"Log EMI - {lb.name}", item.amount, due,
                               self.ctx.account_options_active(), lb.account_id,
                               "Records the payment and reduces what you owe by the principal part.",
                               self)
        if dlg.exec():
            amount, when, account_id = dlg.values()
            try:
                self.ctx.recurring_service.log(item, amount, when, account_id)
            except ValueError as e:
                QMessageBox.warning(self, "Couldn't log EMI", str(e))
                return
            self.refresh()
            notify("EMI logged")

    def _edit(self) -> None:
        lb = self.selected()
        if lb is None:
            return
        dlg = LiabilityDialog(self, lb, accounts=self.ctx.account_options_active())
        if dlg.exec() == LiabilityDialog.DialogCode.Accepted:
            self.ctx.liability_service.update(dlg.get_liability())
            self.refresh()
            notify("Saved")

    def _toggle(self) -> None:
        lb = self.selected()
        if lb is not None:
            self.ctx.liability_service.toggle_active(lb)
            self.refresh()

    def _delete(self) -> None:
        lb = self.selected()
        if lb is None:
            return
        ans = QMessageBox.question(
            self, "Delete liability",
            f"Delete “{lb.name}”? This can't be undone. "
            "(To keep its history, use “Mark closed” instead.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if ans == QMessageBox.StandardButton.Yes:
            self.ctx.liability_service.delete(lb.id)
            self._selected_id = None
            self.refresh()
            notify("Deleted")
