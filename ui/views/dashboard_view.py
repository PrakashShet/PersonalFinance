"""Dashboard - your money at a glance, and what needs doing.

Order of the page follows what you'd ask first: what am I worth and how is it
moving; what needs my attention (payments due, income to record); then where
the money is, goals, and what happened recently.
"""
from __future__ import annotations

from datetime import date
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from services.app_context import AppContext
from services.budget_service import STATE_OVER, BudgetStatus
from services.recurring_service import (
    ACTION_DONE,
    ACTION_LOG,
    ACTION_RECORD,
    KIND_EMI,
    KIND_INCOME,
    KIND_MATURITY,
    KIND_PREMIUM,
    KIND_REMINDER,
    KIND_SIP,
    DueItem,
)
from ui import navigation
from ui.dialogs.quick_dialogs import LogPaymentDialog, ReminderDialog
from ui.dialogs.record_income_dialog import RecordIncomeDialog
from ui.helpers.budget_text import alert_texts
from ui.views.investments_view import ALLOC_LABELS, ALLOC_ORDER
from ui.widgets.charts import SegmentedBar, TrendChart
from ui.widgets.common import (
    ActivityRow,
    Banner,
    Card,
    PageHeader,
    StatGrid,
    button,
    clear_layout,
    label,
    progress,
)
from ui.widgets.toast import notify
from utils.formatters import fmt_date, fmt_inr, fmt_money
from utils.logger import get_logger

log = get_logger(__name__)

_KIND_ICON = {
    KIND_SIP: "investments", KIND_EMI: "liabilities", KIND_PREMIUM: "shield",
    KIND_INCOME: "income", KIND_MATURITY: "calendar", KIND_REMINDER: "bell",
}


def _greeting() -> str:
    from datetime import datetime

    h = datetime.now().hour
    return "Good morning" if h < 12 else ("Good afternoon" if h < 17 else "Good evening")


def _compact(v: float) -> str:
    return fmt_inr(v, compact=True)


class DashboardView(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._topics = {
            "accounts", "transactions", "income_sources", "income_entries", "holdings",
            "liabilities", "goals", "goal_holdings", "reminders", "fx_rates", "budgets",
        }
        self._dirty = True
        self.ctx.events.changed.connect(self._on_data_changed)
        self._build()
        self.refresh()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(28, 24, 28, 28)
        root.setSpacing(18)
        scroll.setWidget(page)
        outer.addWidget(scroll)

        self.header = PageHeader(
            _greeting(), date.today().strftime("%A, %d %B %Y"),
            [button("Add transaction", "primary", "plus",
                    on_click=lambda: navigation.go("transactions", add="expense"),
                    tooltip="Ctrl+N")])
        root.addWidget(self.header)

        self.banners = QVBoxLayout()
        self.banners.setSpacing(8)
        root.addLayout(self.banners)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(18)
        root.addLayout(grid)

        # Row 1 - net worth | this month
        self.nw_card = Card("Net worth", "Everything you own minus everything you owe")
        self.nw_value = label("-", "heroValue")
        self.nw_change = label("", "kpiHint")
        self.nw_card.body.addWidget(self.nw_value)
        self.nw_card.body.addWidget(self.nw_change)
        self.nw_stats = StatGrid(columns=4)
        self.nw_card.body.addWidget(self.nw_stats)
        grid.addWidget(self.nw_card, 0, 0)

        self.month_card = Card("This month", date.today().strftime("%B %Y"),
                               action=button("Details", "link",
                                             on_click=lambda: navigation.go("transactions", period="This month")))
        self.month_stats = StatGrid(columns=2)
        self.month_card.body.addWidget(self.month_stats)
        self.saved_label = label("", "small")
        self.month_card.body.addWidget(self.saved_label)
        self.saved_bar = progress(0)
        self.month_card.body.addWidget(self.saved_bar)
        grid.addWidget(self.month_card, 0, 1)

        # Row 2 - needs attention | trend
        self.attention_card = Card("Needs attention",
                                   "Payments due, income to record, budgets running out",
                                   action=button("Reminder", "ghost", "plus",
                                                 on_click=self._add_reminder, size="small"))
        self.attention_list = QVBoxLayout()
        self.attention_list.setSpacing(2)
        self.attention_card.body.addLayout(self.attention_list)
        self.attention_card.body.addStretch(1)
        grid.addWidget(self.attention_card, 1, 0)

        self.trend_card = Card("Net worth over time", "One snapshot per day you use the app")
        self.trend = TrendChart(_compact, height=230)
        self.trend_card.body.addWidget(self.trend)
        grid.addWidget(self.trend_card, 1, 1)

        # Row 3 - allocation | goals | recent
        row3 = QHBoxLayout()
        row3.setSpacing(18)
        self.alloc_card = Card("Where your money is", "Investments by type",
                               action=button("Investments", "link",
                                             on_click=lambda: navigation.go("investments")))
        self.alloc = SegmentedBar(_compact)
        self.alloc_card.body.addWidget(self.alloc)
        self.alloc_card.body.addStretch(1)
        row3.addWidget(self.alloc_card, 1)

        self.goals_card = Card("Goals", "Progress towards your targets",
                               action=button("All goals", "link", on_click=lambda: navigation.go("goals")))
        self.goals_list = QVBoxLayout()
        self.goals_list.setSpacing(12)
        self.goals_card.body.addLayout(self.goals_list)
        self.goals_card.body.addStretch(1)
        row3.addWidget(self.goals_card, 1)

        self.recent_card = Card("Recent transactions", "",
                                action=button("View all", "link", on_click=lambda: navigation.go("transactions")))
        self.recent_list = QVBoxLayout()
        self.recent_list.setSpacing(0)
        self.recent_card.body.addLayout(self.recent_list)
        self.recent_card.body.addStretch(1)
        row3.addWidget(self.recent_card, 1)
        root.addLayout(row3)

        grid.setColumnStretch(0, 5)
        grid.setColumnStretch(1, 6)
        root.addStretch(1)

    # ------------------------------------------------------------------ data
    def _on_data_changed(self, topic: str) -> None:
        if topic in self._topics:
            self._dirty = True

    def mark_dirty(self) -> None:
        self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty:
            self.refresh()

    def refresh(self) -> None:
        self.header.title.setText(_greeting())
        for fn in (self._refresh_banners, self._refresh_networth, self._refresh_month,
                   self._refresh_attention, self._refresh_trend, self._refresh_allocation,
                   self._refresh_goals, self._refresh_recent):
            try:
                fn()
            except Exception:
                # Never let one card take the page down - but never hide it either.
                log.exception(f"Dashboard: {fn.__name__} failed")
        self._dirty = False

    def _refresh_banners(self) -> None:
        clear_layout(self.banners)
        missing = self.ctx.currencies_missing_rates()
        if missing:
            self.banners.addWidget(Banner(
                f"Balances in {', '.join(missing)} aren't included in your totals yet. "
                "Add an exchange rate so they count.", "warning", "Add rate",
                lambda: navigation.go("settings")))
        mismatches = self.ctx.account_service.reconciliation_report()
        if mismatches:
            names = ", ".join(m.account.name for m in mismatches[:3])
            self.banners.addWidget(Banner(
                f"{names}: the balance doesn't match its transactions. Open the account to reconcile.",
                "warning", "Open Accounts", lambda: navigation.go("accounts")))

    def _refresh_networth(self) -> None:
        nw = self.ctx.net_worth_service
        bs = nw.compute()
        self.nw_value.setText(fmt_inr(bs.net_worth, decimals=0))
        change = nw.change_since(30)
        if change is None:
            self.nw_change.setText("Change over time shows up once there's a month of history.")
            self.nw_change.setProperty("tone", "")
        elif abs(change.amount) < 1:
            self.nw_change.setText(f"No change since {fmt_date(change.since, '%d %b')}")
            self.nw_change.setProperty("tone", "")
        else:
            up = change.amount >= 0
            self.nw_change.setText(
                f"{'▲' if up else '▼'} {fmt_inr(abs(change.amount), compact=True)} since "
                f"{fmt_date(change.since, '%d %b')}")
            self.nw_change.setProperty("tone", "positive" if up else "negative")
        self.nw_change.style().unpolish(self.nw_change)
        self.nw_change.style().polish(self.nw_change)
        self.nw_stats.set_items([
            ("Cash & bank", _compact(bs.cash_and_bank)),
            ("Investments", _compact(bs.investments)),
            ("Total assets", _compact(bs.total_assets)),
            ("Liabilities", _compact(bs.total_liabilities), "negative" if bs.total_liabilities else None),
        ])

    def _refresh_month(self) -> None:
        today = date.today()
        s = self.ctx.transaction_service.summary(year=str(today.year), month=f"{today.month:02d}")
        income, spent, invested, net = s["income"], s["expense"], s["invested"], s["net"]
        self.month_stats.set_items([
            ("Income", _compact(income), "positive" if income else None),
            ("Spent", _compact(spent)),
            ("Invested", _compact(invested)),
            ("Saved", ("" if net >= 0 else "−") + _compact(abs(net)),
             "positive" if net > 0 else ("negative" if net < 0 else None)),
        ])
        if income > 0:
            rate = max(0.0, min(100.0, (income - spent) / income * 100))
            self.saved_label.setText(f"You kept {rate:.0f}% of this month's income after spending.")
            self.saved_bar.setValue(int(rate * 10))
            self.saved_bar.setProperty("tone", "positive" if rate >= 20 else "warning")
            self.saved_bar.style().unpolish(self.saved_bar)
            self.saved_bar.style().polish(self.saved_bar)
            self.saved_bar.setVisible(True)
        else:
            self.saved_label.setText("No income recorded this month yet.")
            self.saved_bar.setVisible(False)

    def _refresh_attention(self) -> None:
        clear_layout(self.attention_list)
        items = self.ctx.recurring_service.due_items()
        alerts = self.ctx.budget_service.alerts()
        # Overdue payments, then budgets already over, then what's coming up,
        # then budgets close to their limit.
        rows = ([lambda i=i: self._attention_row(i) for i in items if i.overdue]
                + [lambda s=s: self._budget_row(s) for s in alerts if s.state == STATE_OVER]
                + [lambda i=i: self._attention_row(i) for i in items if not i.overdue]
                + [lambda s=s: self._budget_row(s) for s in alerts if s.state != STATE_OVER])
        if not rows:
            detail = "Nothing due in the next two weeks"
            if self.ctx.budget_service.list_all():
                detail += ", and every budget has room"
            empty = ActivityRow("", "All caught up", detail + ".",
                                icon_name="check_circle", icon_token="positive")
            self.attention_list.addWidget(empty)
            return
        for make in rows[:8]:
            self.attention_list.addWidget(make())
        if len(rows) > 8:
            self.attention_list.addWidget(label(f"+ {len(rows) - 8} more", "small"))

    def _budget_row(self, status: BudgetStatus) -> QWidget:
        title, detail = alert_texts(status)
        action = button("View", "secondary", size="small",
                        on_click=lambda b=status.budget.id: navigation.go("budgets", budget_id=b))
        token = "negative" if status.state == STATE_OVER else "warning"
        return ActivityRow("", title, detail, "", None, action, icon_name="budget", icon_token=token)

    def _attention_row(self, item: DueItem) -> QWidget:
        if item.kind == KIND_INCOME:
            when = item.note or "This month"
        else:
            d = date.fromisoformat(item.due_date)
            delta = (d - date.today()).days
            when = ("Overdue · " if item.overdue else "") + (
                "Due today" if delta == 0 else
                f"Due {fmt_date(item.due_date, '%d %b')}" if delta > 0 else
                f"Was due {fmt_date(item.due_date, '%d %b')}")
            if item.kind == KIND_MATURITY:
                when = f"Matures {fmt_date(item.due_date, '%d %b')}" + (f" · {item.note}" if item.note else "")
        action = None
        if item.action == ACTION_LOG:
            action = button("Log", "secondary", size="small", on_click=lambda i=item: self._log(i))
        elif item.action == ACTION_RECORD:
            action = button("Record", "secondary", size="small", on_click=lambda i=item: self._record(i))
        elif item.action == ACTION_DONE:
            action = button("Done", "secondary", size="small", on_click=lambda i=item: self._done(i))
        token = "negative" if item.overdue else ("warning" if item.kind == KIND_INCOME else "text_muted")
        return ActivityRow("", item.title, when,
                           fmt_inr(item.amount, compact=True) if item.amount else "",
                           None, action, icon_name=_KIND_ICON.get(item.kind, "clock"), icon_token=token)

    def _refresh_trend(self) -> None:
        points = [(s.snapshot_date, s.net_worth) for s in self.ctx.net_worth_service.history()]
        self.trend.set_points(points, "Your net-worth trend appears after a couple of days of use.")

    def _refresh_allocation(self) -> None:
        alloc = self.ctx.investment_service.asset_allocation()
        self.alloc.set_parts([(k, ALLOC_LABELS.get(k, k.title()), alloc.get(k, 0.0))
                              for k in ALLOC_ORDER + ["other"]], order=ALLOC_ORDER,
                             empty_text="Add investments to see how your money is spread.")

    def _refresh_goals(self) -> None:
        clear_layout(self.goals_list)
        goals = self.ctx.goal_service.list_active()
        if not goals:
            self.goals_list.addWidget(label("No goals yet. Set one to see what it takes each month.",
                                            "muted", wrap=True))
            return
        svc = self.ctx.goal_service
        for g in sorted(goals, key=lambda g: (g.priority or 3, g.target_date or "9999"))[:4]:
            box = QVBoxLayout()
            box.setSpacing(5)
            head = QHBoxLayout()
            head.addWidget(label(g.name, "rowTitle"), 1)
            head.addWidget(label(f"{g.progress_pct:.0f}%", "rowValue"))
            box.addLayout(head)
            box.addWidget(progress(g.progress_pct, "positive" if g.progress_pct >= 100 else ""))
            sip = svc.required_sip(g)
            meta = f"{_compact(g.current_amount)} of {_compact(g.target_amount)}"
            if sip > 0:
                meta += f" · {_compact(sip)}/mo needed"
            box.addWidget(label(meta, "rowMeta"))
            holder = QWidget()
            holder.setLayout(box)
            self.goals_list.addWidget(holder)

    def _refresh_recent(self) -> None:
        clear_layout(self.recent_list)
        rows = self.ctx.transaction_service.recent(6)
        if not rows:
            self.recent_list.addWidget(label("No transactions yet.", "muted"))
            return
        svc = self.ctx.transaction_service
        for r in rows:
            signed = svc.signed_amount(r["txn_type"], r["amount"])
            title = r["description"] or r["category_name"] or r["txn_type"].replace("_", " ").title()
            category = r["category_name"] if r["description"] else None
            meta = " · ".join(x for x in [category, r["account_name"]] if x)
            self.recent_list.addWidget(ActivityRow(
                fmt_date(r["txn_date"], "%d %b"), title, meta,
                ("+" if signed > 0 else "−") + fmt_money(abs(signed), r["account_currency"] or "INR"),
                "positive" if signed > 0 else None))

    # --------------------------------------------------------------- actions
    def _log(self, item: DueItem) -> None:
        dlg = LogPaymentDialog(item.title, item.amount, item.due_date,
                               self.ctx.account_options_active(),
                               item.account_id or self.ctx.preferences.get("last_account_id"),
                               parent=self)
        if dlg.exec():
            amount, when, account_id = dlg.values()
            try:
                self.ctx.recurring_service.log(item, amount, when, account_id)
            except ValueError as e:
                QMessageBox.warning(self, "Couldn't log", str(e))
                return
            notify(f"Logged {item.title}")
            self.refresh()

    def _record(self, item: DueItem) -> None:
        svc = self.ctx.income_source_service
        source = svc.get(item.ref_id)
        if source is None:
            return
        dlg = RecordIncomeDialog(source, self.ctx.account_options_active(),
                                 expected_net=svc.net_monthly(source), parent=self)
        if dlg.exec() == RecordIncomeDialog.DialogCode.Accepted:
            try:
                svc.record_month(source, **dlg.get_values())
            except ValueError as e:
                QMessageBox.warning(self, "Couldn't record", str(e))
                return
            notify(f"Recorded {source.name}")
            self.refresh()

    def _done(self, item: DueItem) -> None:
        self.ctx.recurring_service.complete_reminder(item.ref_id)
        notify("Reminder done")
        self.refresh()

    def _add_reminder(self) -> None:
        dlg = ReminderDialog(self)
        if dlg.exec():
            try:
                self.ctx.recurring_service.add_reminder(**dlg.values())
            except ValueError as e:
                QMessageBox.warning(self, "Couldn't add reminder", str(e))
                return
            notify("Reminder added")
            self.refresh()

