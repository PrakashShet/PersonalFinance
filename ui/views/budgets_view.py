"""Budgets - a monthly or yearly spending limit per category: how much is
spent, how much is left, and how recent months compare."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtWidgets import QHBoxLayout, QMessageBox, QVBoxLayout, QWidget

from services.budget_service import (
    MONTHLY,
    STATE_NEAR,
    STATE_OK,
    STATE_OVER,
    YEARLY,
    BudgetStatus,
    PeriodSpend,
    period_label,
    typical_spend,
)
from ui import navigation
from ui.dialogs.budget_dialog import BudgetDialog
from ui.helpers.budget_text import (
    PERIOD_NAMES,
    STATE_BADGE,
    STATE_TONE,
    allowance_text,
    left_text,
    money,
)
from ui.views.master_detail import MasterDetailView
from ui.widgets.common import Banner, SegmentedControl, clear_layout, label, progress
from ui.widgets.detail_panel import DetailPanel
from ui.widgets.kpi_card import KpiCard
from ui.widgets.list_tile import ListTile
from ui.widgets.toast import notify
from utils.formatters import fmt_money

FILTERS = [("all", "All"), (MONTHLY, "Monthly"), (YEARLY, "Yearly")]


class BudgetsView(MasterDetailView):
    title = "Budgets"
    subtitle = "A monthly or yearly spending limit for any category - and what's left of it."
    add_label = "Add budget"
    topics = frozenset({"budgets", "transactions", "categories", "accounts", "fx_rates"})
    inactive_label = None
    empty_icon = "budget"
    empty_title = "No budgets yet"
    empty_text = ("Give a category a limit - groceries, eating out, travel - and see how "
                  "much is left as you spend.")
    select_hint = "Select a budget to see this period's spending and how recent ones compare."

    def __init__(self, ctx) -> None:
        self._filter = "all"
        super().__init__(ctx)

    # ------------------------------------------------------------------ hooks
    def build_kpis(self):
        self.k_month = KpiCard("Spent this month", icon_name="budget")
        self.k_left = KpiCard("Left this month", icon_name="wallet")
        self.k_year = KpiCard("Spent this year", icon_name="calendar")
        self.k_over = KpiCard("Over the limit", icon_name="alert")
        return [self.k_month, self.k_left, self.k_year, self.k_over]

    def build_extra(self):
        self.extra = QWidget()
        self.extra_lay = QVBoxLayout(self.extra)
        self.extra_lay.setContentsMargins(0, 0, 0, 0)
        self.extra_lay.setSpacing(8)
        return self.extra

    def build_filters(self):
        self.filter_seg = SegmentedControl(FILTERS, "all")
        self.filter_seg.changed.connect(self._on_filter)
        return self.filter_seg

    def fetch(self, include_inactive: bool):
        return self.ctx.budget_service.statuses()

    def item_id(self, s: BudgetStatus):
        return s.budget.id

    def filter_items(self, items):
        if self._filter == "all":
            return items
        return [s for s in items if s.period == self._filter]

    def refresh_kpis(self, items) -> None:
        svc = self.ctx.budget_service
        # Exact rupees, not compact: "₹31.1 K of ₹34.5 K, ₹3.5 K left" doesn't add up.
        m = svc.totals(items, MONTHLY)
        if m.count:
            self.k_month.set_value(money(m.spent))
            self.k_month.set_hint(f"of {money(m.limit)} in monthly limits")
            if m.remaining >= 0:
                self.k_left.set_value(money(m.remaining))
            else:
                self.k_left.set_value(f"{money(-m.remaining)} over", "negative")
            days = next((s.days_left for s in items if s.period == MONTHLY), 0)
            self.k_left.set_hint(f"{days} day{'' if days == 1 else 's'} to go")
        else:
            self.k_month.set_value("-")
            self.k_month.set_hint("No monthly limits yet")
            self.k_left.set_value("-")
            self.k_left.set_hint("")

        start, _end = svc.current_bounds(YEARLY)
        year = period_label(YEARLY, start)
        self.k_year.title_label.setText(f"Spent in {year}")
        y = svc.totals(items, YEARLY)
        if y.count:
            self.k_year.set_value(money(y.spent))
            self.k_year.set_hint(f"of {money(y.limit)} in yearly limits")
        else:
            self.k_year.set_value("-")
            self.k_year.set_hint("No yearly limits yet")

        over = [s for s in items if s.state == STATE_OVER]
        near = [s for s in items if s.state == STATE_NEAR]
        self.k_over.set_value(str(len(over)), "negative" if over else None)
        if over:
            more = f" and {len(over) - 1} more" if len(over) > 1 else ""
            self.k_over.set_hint(f"{over[0].category_name}{more}", "negative")
        elif near:
            self.k_over.set_hint(f"{len(near)} near the limit", "warning")
        elif items:
            self.k_over.set_hint("Everything within its limit", "positive")
        else:
            self.k_over.set_hint("")
        self._refresh_banners(items)

    def _refresh_banners(self, items) -> None:
        clear_layout(self.extra_lay)
        unconverted: dict[str, float] = {}
        for s in items:
            for ccy, v in s.unconverted.items():
                unconverted[ccy] = unconverted.get(ccy, 0.0) + v
        if unconverted:
            self.extra_lay.addWidget(Banner(
                f"Spending in {', '.join(sorted(unconverted))} isn't counted in your budgets yet. "
                "Add an exchange rate so it counts.", "warning", "Add rate",
                lambda: navigation.go("settings")))
        unbudgeted = self.ctx.budget_service.unbudgeted()
        if unbudgeted:
            total = sum(u.spent for u in unbudgeted)
            parts = ", ".join(f"{u.name} {money(u.spent)}" for u in unbudgeted[:3])
            if len(unbudgeted) > 3:
                parts += f" and {len(unbudgeted) - 3} more"
            first = next((u.category_id for u in unbudgeted if u.category_id is not None), None)
            self.extra_lay.addWidget(Banner(
                f"{money(total)} spent this month without a limit: {parts}.", "info",
                "Add budget" if first is not None else "",
                (lambda c=first: self.on_add(c)) if first is not None else None))
        self.extra.setVisible(self.extra_lay.count() > 0)

    def make_tile(self, s: BudgetStatus, selected: bool) -> ListTile:
        return ListTile(
            s.budget.id, s.category_name,
            f"{PERIOD_NAMES.get(s.period, s.period)} · {money(s.spent)} of {money(s.limit)}",
            value=left_text(s), value_tone="negative" if s.state == STATE_OVER else None,
            badge=STATE_BADGE.get(s.state), progress_pct=s.pct,
            progress_tone=STATE_TONE[s.state], icon_name="budget", selected=selected,
        )

    def render_detail(self, s: BudgetStatus, panel: DetailPanel) -> None:
        badges = [STATE_BADGE[s.state]] if s.state in STATE_BADGE else []
        panel.set_header(s.category_name, f"{PERIOD_NAMES.get(s.period, '')} limit · {s.label}",
                         badges)
        panel.set_actions([
            ("Edit", self._edit, "primary", "edit"),
            ("See transactions", self._open_transactions, "secondary", "transactions"),
            ("Delete", self._delete, "danger", "trash"),
        ])

        bar = progress(s.pct, STATE_TONE[s.state], large=True)
        panel.add_section(f"{s.pct:.0f}% of the limit used", bar)

        rows = [("Limit", money(s.limit)), ("Spent", money(s.spent))]
        if s.state == STATE_OVER:
            rows.append(("Over by", money(-s.remaining), "negative"))
        else:
            rows.append(("Left", money(s.remaining),
                         "positive" if s.state == STATE_OK else "warning"))
        panel.add_stats(s.label, rows)
        hint = allowance_text(s)
        if hint:
            panel.add_text(hint + ".")
        if s.unconverted:
            amounts = ", ".join(fmt_money(v, c) for c, v in sorted(s.unconverted.items()))
            panel.add_banner(f"{amounts} spent from accounts in other currencies isn't counted "
                             "here yet. Add an exchange rate so it counts.", "warning",
                             "Add rate", lambda: navigation.go("settings"))

        periods = 6 if s.period == MONTHLY else 3
        history = self.ctx.budget_service.history(s.budget.id, periods)
        if history:
            title = "Last 6 months" if s.period == MONTHLY else "Last 3 years"
            panel.add_section(title, self._history_widget(history))
            typical = typical_spend(history)
            if typical is not None:
                unit = "month" if s.period == MONTHLY else "year"
                panel.add_text(f"A typical {unit} before this one: {money(typical)} "
                               f"(counting only {unit}s with spending recorded).", "small")
        if s.budget.notes:
            panel.add_text(s.budget.notes)

    @staticmethod
    def _history_widget(history: list[PeriodSpend]) -> QWidget:
        holder = QWidget()
        col = QVBoxLayout(holder)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(12)
        for p in reversed(history):                          # newest first
            box = QVBoxLayout()
            box.setContentsMargins(0, 0, 0, 0)
            box.setSpacing(5)
            head = QHBoxLayout()
            head.addWidget(label(p.label + (" · so far" if p.current else ""), "rowTitle"), 1)
            if p.logged:
                head.addWidget(label(f"{money(p.spent)} · {p.pct:.0f}%", "rowValue",
                                     tone=STATE_TONE[p.state] or None))
            else:
                head.addWidget(label("Nothing recorded", "rowMeta"))
            box.addLayout(head)
            box.addWidget(progress(p.pct, STATE_TONE[p.state]))
            row = QWidget()
            row.setLayout(box)
            col.addWidget(row)
        return holder

    # ----------------------------------------------------------------- actions
    def on_add(self, category_id: Optional[int] = None) -> None:
        svc = self.ctx.budget_service
        categories = self.ctx.expense_categories()
        if not categories:
            QMessageBox.information(self, "No categories", "There are no spending categories yet.")
            return
        dlg = BudgetDialog(categories, existing=self._existing, suggest=self._suggest,
                           year_text=self._year_text(), category_id=category_id, parent=self)
        if dlg.exec() != BudgetDialog.DialogCode.Accepted:
            return
        v = dlg.values()
        try:
            self._selected_id = svc.set_limit(v["category_id"], v["period"], v["amount"], v["notes"])
        except ValueError as e:
            QMessageBox.warning(self, "Couldn't save", str(e))
            return
        if self._filter not in ("all", v["period"]):
            self.filter_seg.set_current("all")
            self._filter = "all"
        self.refresh()
        notify("Budget saved")

    def on_activate(self, s: BudgetStatus) -> None:
        self._edit()

    def show_with(self, budget_id: Optional[int] = None, add: bool = False,
                  category_id: Optional[int] = None, **_kw) -> None:
        if add:
            self.on_add(category_id)
            return
        if budget_id is not None:
            self._filter = "all"
            self.filter_seg.set_current("all")
            self._selected_id = budget_id
            self.refresh()

    def _on_filter(self, key: str) -> None:
        self._filter = key
        self._selected_id = None
        self.refresh()

    def _existing(self, category_id: int, period: str):
        return next((b for b in self.ctx.budget_service.for_category(category_id)
                     if b.period == period), None)

    def _suggest(self, category_id: int, period: str):
        return self.ctx.budget_service.suggestion(category_id, period)

    def _year_text(self) -> str:
        if self.ctx.budget_service.year_start() == 4:
            return "April to March (the financial year)"
        return "January to December"

    def _edit(self) -> None:
        s = self.selected()
        if s is None:
            return
        svc = self.ctx.budget_service
        dlg = BudgetDialog(self.ctx.expense_categories(), budget=s.budget,
                           existing=self._existing, suggest=self._suggest,
                           year_text=self._year_text(), parent=self)
        if dlg.exec() != BudgetDialog.DialogCode.Accepted:
            return
        try:
            svc.update(dlg.get_budget())
        except ValueError as e:
            QMessageBox.warning(self, "Couldn't save", str(e))
            return
        self.refresh()
        notify("Saved")

    def _delete(self) -> None:
        s = self.selected()
        if s is None:
            return
        ans = QMessageBox.question(
            self, "Delete budget",
            f"Remove the {s.period} limit on {s.category_name}? Your transactions aren't affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if ans == QMessageBox.StandardButton.Yes:
            self.ctx.budget_service.delete(s.budget.id)
            self._selected_id = None
            self.refresh()
            notify("Budget removed")

    def _open_transactions(self) -> None:
        s = self.selected()
        if s is None:
            return
        navigation.go("transactions", category_id=s.budget.category_id, txn_type="expense",
                      date_from=s.start.isoformat(), date_to=s.end.isoformat(),
                      period_label=s.label)
