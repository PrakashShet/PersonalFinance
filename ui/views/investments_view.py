"""Investments - what you own, what it's worth, and how it's doing.

Term insurance lives under "Protection": it is cover, not an investment, so it
never counts toward invested amounts, returns or movers.
"""
from __future__ import annotations

from datetime import date

from PyQt6.QtWidgets import QMessageBox

from config.constants import ASSET_BUCKETS
from models.holding import Holding
from services.recurring_service import KIND_SIP, DueItem
from ui.dialogs.holding_dialog import HoldingDialog
from ui.dialogs.quick_dialogs import LogPaymentDialog
from ui.theme.badges import HOLDING_LABELS, label as type_label
from ui.views.master_detail import MasterDetailView
from ui.widgets.charts import SegmentedBar
from ui.widgets.common import Card, SegmentedControl
from ui.widgets.detail_panel import DetailPanel
from ui.widgets.kpi_card import KpiCard
from ui.widgets.list_tile import ListTile
from ui.widgets.toast import notify
from utils.formatters import fmt_date, fmt_inr, fmt_pct

BUCKETS = [("all", "All"), ("equity", "Equity"), ("debt", "Debt"), ("gold", "Gold"),
           ("alt", "Alternatives"), ("protection", "Protection")]
# Fixed colour order (identity, not rank): see ui/widgets/charts.py
# Equity/debt/gold are the common trio and take the first three slots, which
# pass the colour-blindness checks in any combination; "alt" (often absent)
# goes last so its absence never puts an unvalidated pair side by side.
ALLOC_ORDER = ["equity", "debt", "gold", "alt"]
ALLOC_LABELS = {"equity": "Equity", "debt": "Debt", "alt": "Alternatives", "gold": "Gold",
                "other": "Other"}
_BUCKET_TYPES = {k: {t.value for t in v} for k, v in ASSET_BUCKETS.items()}
_TYPE_ICON = {"term_insurance": "shield", "gold_coin": "coins", "gold_jewelry": "coins"}

_STOCK = {"stock", "etf", "crypto"}
_FUND = {"sip", "mutual_fund"}
_FIXED = {"fd", "bond", "ppf", "epf", "nps"}
_GOLD = {"gold_coin", "gold_jewelry"}


def _signed_pct(v: float) -> str:
    return ("+" if v >= 0 else "−") + fmt_pct(abs(v))


class InvestmentsView(MasterDetailView):
    title = "Investments"
    subtitle = "Stocks, funds, deposits, gold and more - with returns that account for timing."
    add_label = "Add investment"
    topics = frozenset({"holdings", "accounts", "transactions", "goal_holdings"})
    inactive_label = "Show sold / closed"
    empty_icon = "investments"
    empty_title = "No investments here"
    empty_text = "Add what you own - funds, stocks, deposits, gold - to see it grow."
    select_hint = "Select an investment to see its value, return and details."

    def __init__(self, ctx) -> None:
        self._bucket = "all"
        super().__init__(ctx)

    # ------------------------------------------------------------- hooks
    def build_kpis(self):
        self.k_value = KpiCard("Current value", icon_name="investments")
        self.k_invested = KpiCard("Invested", icon_name="coins")
        self.k_gain = KpiCard("Gain / loss", icon_name="income")
        self.k_xirr = KpiCard("Annual return (XIRR)", icon_name="repeat")
        return [self.k_value, self.k_invested, self.k_gain, self.k_xirr]

    def build_extra(self):
        card = Card("Allocation", padding=16, spacing=10)
        self.alloc = SegmentedBar(lambda v: fmt_inr(v, compact=True), compact=True)
        card.body.addWidget(self.alloc)
        return card

    def build_filters(self):
        self.bucket_seg = SegmentedControl(BUCKETS, "all")
        self.bucket_seg.changed.connect(self._on_bucket)
        return self.bucket_seg

    def fetch(self, include_inactive: bool):
        return self.ctx.investment_service.list_all(include_inactive)

    def filter_items(self, items):
        if self._bucket == "all":
            return items
        if self._bucket == "protection":
            return [h for h in items if self.ctx.investment_service.is_protection(h)]
        allowed = _BUCKET_TYPES.get(self._bucket, set())
        return [h for h in items if h.holding_type in allowed]

    def refresh_kpis(self, items) -> None:
        svc = self.ctx.investment_service
        s = svc.portfolio_summary()
        self.k_value.set_value(fmt_inr(s.value, compact=True))
        self.k_value.set_hint(f"{s.count} investment{'s' if s.count != 1 else ''}")
        self.k_invested.set_value(fmt_inr(s.invested, compact=True))
        tone = "positive" if s.pnl >= 0 else "negative"
        self.k_gain.set_value(("+" if s.pnl >= 0 else "−") + fmt_inr(abs(s.pnl), compact=True), tone)
        self.k_gain.set_hint(_signed_pct(s.return_pct) + " overall", tone)
        if s.annualised is None:
            self.k_xirr.set_value("-")
            self.k_xirr.set_hint("Needs purchase dates")
        else:
            t = "positive" if s.annualised >= 0 else "negative"
            self.k_xirr.set_value(_signed_pct(s.annualised * 100), t)
            self.k_xirr.set_hint("per year, timing-aware")
        alloc = svc.asset_allocation()
        self.alloc.set_parts([(k, ALLOC_LABELS.get(k, k.title()), alloc.get(k, 0.0))
                              for k in ALLOC_ORDER + ["other"]], order=ALLOC_ORDER,
                             empty_text="Add investments to see how your money is spread.")

    def make_tile(self, h: Holding, selected: bool) -> ListTile:
        svc = self.ctx.investment_service
        meta = " · ".join(x for x in [type_label(HOLDING_LABELS, h.holding_type), h.institution] if x)
        if svc.is_protection(h):
            return ListTile(h.id, h.name, meta,
                            value=fmt_inr(h.sum_assured or 0, compact=True) + " cover",
                            chip=(f"{fmt_inr(h.premium_amount or 0, compact=True)}/yr", "neutral")
                            if h.premium_amount else None,
                            badge=("Closed", "neutral") if not h.is_active else None,
                            icon_name="shield", muted=not h.is_active, selected=selected)
        ret = h.return_pct
        chip = (_signed_pct(ret), "positive" if ret >= 0 else "negative") if h.invested_amount else None
        return ListTile(h.id, h.name, meta, value=fmt_inr(h.current_value), chip=chip,
                        badge=("Closed", "neutral") if not h.is_active else None,
                        icon_name=_TYPE_ICON.get(h.holding_type, "investments"),
                        muted=not h.is_active, selected=selected)

    def on_add(self) -> None:
        dlg = HoldingDialog(self, accounts=self.ctx.account_options_active(),
                            stock_lookup=self.ctx.investment_service.lookup_stock)
        if dlg.exec() == HoldingDialog.DialogCode.Accepted:
            h = dlg.get_holding()
            self._selected_id = self.ctx.investment_service.add_holding(h)
            self.refresh()
            notify(f"Added {h.name}")

    def on_activate(self, h: Holding) -> None:
        self._edit()

    def _on_bucket(self, key: str) -> None:
        self._bucket = key
        self._selected_id = None
        self.refresh()

    # ------------------------------------------------------------ detail
    def render_detail(self, h: Holding, panel: DetailPanel) -> None:
        svc = self.ctx.investment_service
        accounts = self.ctx.account_name_map()
        meta = " · ".join(x for x in [type_label(HOLDING_LABELS, h.holding_type), h.institution] if x)
        panel.set_header(h.name, meta, [("Closed", "neutral")] if not h.is_active else [])

        actions = []
        if h.is_active and h.sip_amount:
            actions.append(("Log SIP", self._log_sip, "primary", "check"))
        actions += [("Edit", self._edit, "secondary", "edit"),
                    ("Reopen" if not h.is_active else "Mark sold / closed", self._toggle, "ghost"),
                    ("Delete", self._delete, "danger", "trash")]
        panel.set_actions(actions)

        if svc.is_protection(h):
            rows = [("Cover", fmt_inr(h.sum_assured or 0)),
                    ("Premium", f"{fmt_inr(h.premium_amount or 0)} / year")]
            if h.premium_due_date:
                rows.append(("Next premium", fmt_date(h.premium_due_date)))
            if h.policy_term_years:
                rows.append(("Term", f"{h.policy_term_years} years"))
            panel.add_stats("Protection", rows)
            panel.add_text("Insurance is cover, not an investment - it isn't counted in "
                           "invested amounts, returns or net worth.")
        else:
            pnl = h.unrealized_pnl
            tone = "positive" if pnl >= 0 else "negative"
            rows = [("Current value", fmt_inr(h.current_value)),
                    ("Invested", fmt_inr(h.invested_amount)),
                    ("Gain / loss", ("+" if pnl >= 0 else "−") + fmt_inr(abs(pnl))
                     + (f" ({_signed_pct(h.return_pct)})" if h.invested_amount else ""), tone)]
            annual = svc.annualised_return(h)
            rows.append(("Annual return (XIRR)",
                         _signed_pct(annual * 100) if annual is not None else
                         "Add the purchase date", ("positive" if (annual or 0) >= 0 else "negative")
                         if annual is not None else "muted"))
            panel.add_stats("Value", rows, columns=2)

        details = []
        t = h.holding_type
        if h.purchase_date:
            details.append(("Bought", fmt_date(h.purchase_date)))
        if h.folio_or_account:
            details.append(("Folio / account", h.folio_or_account))
        if h.linked_account_id:
            details.append(("Linked account", accounts.get(h.linked_account_id, "-")))
        if t in _STOCK:
            if h.symbol:
                details.append(("Symbol", f"{h.symbol} ({h.exchange or '-'})"))
            if h.quantity:
                details.append(("Quantity", f"{h.quantity:,.4g}"))
            if h.avg_price:
                details.append(("Average price", fmt_inr(h.avg_price)))
            if h.current_price:
                details.append(("Current price", fmt_inr(h.current_price)))
            if h.market_cap:
                details.append(("Market cap", h.market_cap.replace("_", " ").title()))
            if h.sector:
                details.append(("Sector", h.sector))
        elif t in _FUND:
            if h.quantity:
                details.append(("Units", f"{h.quantity:,.4f}"))
            if h.current_price:
                details.append(("NAV", fmt_inr(h.current_price)))
            if h.sip_amount:
                details.append(("SIP", f"{fmt_inr(h.sip_amount)} / month"))
            if h.sip_day_of_month:
                details.append(("SIP date", f"Day {h.sip_day_of_month} of each month"))
        elif t in _FIXED:
            if h.interest_rate:
                details.append(("Interest rate", f"{fmt_pct(h.interest_rate)} a year"))
            if h.maturity_date:
                details.append(("Matures", fmt_date(h.maturity_date)))
            if h.payout_frequency:
                details.append(("Payout", h.payout_frequency.replace("_", " ").title()))
            details.append(("Auto-renew", "Yes" if h.auto_renew else "No"))
        elif t in _GOLD:
            if h.weight_grams:
                details.append(("Weight", f"{h.weight_grams:.3f} g"))
            if h.purity:
                details.append(("Purity", h.purity))
            if h.making_charges:
                details.append(("Making charges", fmt_inr(h.making_charges)))
        if details:
            panel.add_stats("Details", details, columns=2)
        if h.notes:
            panel.add_text(h.notes)

    # ----------------------------------------------------------- actions
    def _log_sip(self) -> None:
        h = self.selected()
        if h is None:
            return
        today = date.today()
        item = DueItem(key=f"sip:{h.id}:{today:%Y-%m}", kind=KIND_SIP, title=f"SIP - {h.name}",
                       due_date=today.isoformat(), amount=float(h.sip_amount or 0),
                       account_id=h.linked_account_id, ref_id=h.id, action="log")
        if self.ctx.transaction_service.has_tag(item.key):
            ok = QMessageBox.question(self, "Already logged",
                                      "This month's SIP is already logged. Log another instalment?")
            if ok != QMessageBox.StandardButton.Yes:
                return
            item.key = f"{item.key}:{today:%d%H%M%S}"
        dlg = LogPaymentDialog(f"Log SIP - {h.name}", item.amount, item.due_date,
                               self.ctx.account_options_active(), h.linked_account_id,
                               "Records the purchase and adds it to this investment's value.", self)
        if dlg.exec():
            amount, when, account_id = dlg.values()
            try:
                self.ctx.recurring_service.log(item, amount, when, account_id)
            except ValueError as e:
                QMessageBox.warning(self, "Couldn't log SIP", str(e))
                return
            self.refresh()
            notify("SIP logged")

    def _edit(self) -> None:
        h = self.selected()
        if h is None:
            return
        dlg = HoldingDialog(self, h, accounts=self.ctx.account_options_active(),
                            stock_lookup=self.ctx.investment_service.lookup_stock)
        if dlg.exec() == HoldingDialog.DialogCode.Accepted:
            self.ctx.investment_service.update_holding(dlg.get_holding())
            self.refresh()
            notify("Saved")

    def _toggle(self) -> None:
        h = self.selected()
        if h is not None:
            self.ctx.investment_service.toggle_active(h)
            self.refresh()

    def _delete(self) -> None:
        h = self.selected()
        if h is None:
            return
        ans = QMessageBox.question(
            self, "Delete investment",
            f"Delete “{h.name}”? This can't be undone. "
            "(To keep its history, use “Mark sold / closed” instead.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if ans == QMessageBox.StandardButton.Yes:
            self.ctx.investment_service.delete_holding(h.id)
            self._selected_id = None
            self.refresh()
            notify("Deleted")
