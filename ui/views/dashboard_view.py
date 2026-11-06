"""Dashboard — detailed overview: KPIs, net-worth trend, allocation, cashflow,
liabilities, goals, top holdings/movers, and upcoming dues.

Charts are preferred over text. Every section is defensive: missing data or a
missing optional dependency (pyqtgraph) degrades gracefully rather than crashing.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from services.app_context import AppContext
from ui.widgets.kpi_card import KpiCard
from utils.formatters import fmt_inr, fmt_pct, fmt_date

try:
    import pyqtgraph as pg
    _HAS_PG = True
except ImportError:  # pragma: no cover
    _HAS_PG = False


BUCKET_LABELS = {
    "equity": "Equity", "debt": "Debt", "gold": "Gold",
    "alt": "Alternatives", "insurance": "Insurance", "other": "Other",
}
ALLOC_COLOURS = {
    "equity": "#3b82f6", "debt": "#f59e0b", "gold": "#eab308",
    "alt": "#8b5cf6", "insurance": "#ec4899", "other": "#9ca3af",
}
CAP_COLOURS = {
    "large_cap": "#3b82f6", "mid_cap": "#22c55e", "small_cap": "#f59e0b",
    "sme": "#ec4899", "unclassified": "#9ca3af",
}

_GREEN = "#6ee7b7"
_RED = "#fca5a5"
_AMBER = "#fbbf24"
_MUTED = "#9c8869"


def _section(title: str) -> tuple[QGroupBox, QVBoxLayout]:
    box = QGroupBox(title)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(8)
    return box, lay


def _kv(label: str, value: str, colour: str = "") -> QWidget:
    """A compact label-over-value cell."""
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(2)
    t = QLabel(label)
    t.setObjectName("kpiTitle")
    val = QLabel(value)
    val.setObjectName("kpiValue")
    style = "font-size:18px; font-weight:700;"
    if colour:
        style += f" color:{colour};"
    val.setStyleSheet(style + " background:transparent;")
    v.addWidget(t)
    v.addWidget(val)
    return w


class _ProportionBar(QFrame):
    """A thin horizontal proportional bar + legend (no external deps)."""

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 2, 0, 2)
        root.setSpacing(6)
        self._bar_row = QHBoxLayout()
        self._bar_row.setSpacing(2)
        root.addLayout(self._bar_row)
        self._legend = QHBoxLayout()
        self._legend.setSpacing(14)
        root.addLayout(self._legend)

    def load(self, parts: dict[str, float], colours: dict[str, str],
             labels: dict[str, str]) -> None:
        for layout in (self._bar_row, self._legend):
            while layout.count():
                it = layout.takeAt(0)
                if it.widget():
                    it.widget().deleteLater()
        total = sum(v for v in parts.values() if v > 0) or 1.0
        any_seg = False
        for key, value in parts.items():
            if value <= 0:
                continue
            any_seg = True
            pct = value / total
            colour = colours.get(key, "#9ca3af")
            seg = QFrame()
            seg.setFixedHeight(12)
            seg.setStyleSheet(f"background:{colour}; border-radius:3px;")
            seg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._bar_row.addWidget(seg, max(1, int(pct * 100)))
            chip = QLabel(f"{labels.get(key, key.title())}  {pct * 100:.0f}%")
            chip.setStyleSheet(f"color:{colour}; font-size:11px; font-weight:600; background:transparent;")
            self._legend.addWidget(chip)
        if not any_seg:
            empty = QLabel("No data yet")
            empty.setStyleSheet("color:#9c8869; font-size:11px; background:transparent;")
            self._bar_row.addWidget(empty)
        self._legend.addStretch()


class DashboardView(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._topics = {
            "accounts",
            "transactions",
            "income_sources",
            "income_entries",
            "holdings",
            "liabilities",
            "goals",
            "goal_holdings",
        }
        self._dirty = True
        self.invest_svc = ctx.investment_service
        self.networth_svc = ctx.net_worth_service
        self.txn_service = ctx.transaction_service
        self.income_svc = ctx.income_service
        self.projection_svc = ctx.projection_service

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
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(16)
        scroll.setWidget(page)
        outer.addWidget(scroll)

        title = QLabel("Dashboard")
        title.setObjectName("pageTitle")
        root.addWidget(title)

        # ── KPI strip (2 x 4) ────────────────────────────────────────────
        grid = QGridLayout()
        grid.setSpacing(12)
        self.kpi_networth  = KpiCard("Net Worth", "—")
        self.kpi_assets    = KpiCard("Total Assets", "—")
        self.kpi_liab      = KpiCard("Liabilities", "—")
        self.kpi_cash      = KpiCard("Cash & Bank", "—")
        self.kpi_invested  = KpiCard("Invested", "—")
        self.kpi_portfolio = KpiCard("Portfolio Value", "—")
        self.kpi_income    = KpiCard("Income (Mo)", "—")
        self.kpi_expense   = KpiCard("Expenses (Mo)", "—")
        cards = [
            self.kpi_networth, self.kpi_assets, self.kpi_liab, self.kpi_cash,
            self.kpi_invested, self.kpi_portfolio, self.kpi_income, self.kpi_expense,
        ]
        for i, w in enumerate(cards):
            grid.addWidget(w, i // 4, i % 4)
        root.addLayout(grid)

        # ── Net-worth trend  |  Asset allocation ─────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(16)

        trend_box, trend_lay = _section("Net-Worth Trend")
        if _HAS_PG:
            pg.setConfigOption("background", "#0f0f0f")
            pg.setConfigOption("foreground", "#c4a878")
            self._trend_plot = pg.PlotWidget()
            self._trend_plot.setMinimumHeight(240)
            self._trend_plot.showGrid(x=True, y=True, alpha=0.2)
            self._trend_plot.setLabel("left", "Value (Rs Lakhs)")
            self._trend_plot.addLegend(offset=(10, 10))
            self._nw_curve = self._trend_plot.plot(pen=pg.mkPen("#6ee7b7", width=2), name="Net Worth")
            self._asset_curve = self._trend_plot.plot(pen=pg.mkPen("#3b82f6", width=2), name="Assets")
            self._liab_curve = self._trend_plot.plot(
                pen=pg.mkPen("#fca5a5", width=2, style=Qt.PenStyle.DashLine), name="Liabilities")
            trend_lay.addWidget(self._trend_plot)
        else:
            self._trend_plot = None
            trend_lay.addWidget(QLabel("Install pyqtgraph to see the trend chart."))
        self._trend_empty = QLabel("The trend builds up as daily snapshots accrue.")
        self._trend_empty.setStyleSheet("color:#9c8869; font-size:11px; background:transparent;")
        self._trend_empty.setVisible(False)
        trend_lay.addWidget(self._trend_empty)
        row1.addWidget(trend_box, 2)

        alloc_box, alloc_lay = _section("Asset Allocation")
        self.alloc_bar = _ProportionBar()
        alloc_lay.addWidget(self.alloc_bar)
        cap_title = QLabel("Stock Cap Mix")
        cap_title.setObjectName("kpiTitle")
        alloc_lay.addWidget(cap_title)
        self.cap_bar = _ProportionBar()
        alloc_lay.addWidget(self.cap_bar)
        alloc_lay.addStretch()
        row1.addWidget(alloc_box, 1)
        root.addLayout(row1)

        # ── This month cashflow  |  Liabilities snapshot ─────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(16)

        cf_box, cf_lay = _section("This Month")
        self.cf_grid = QGridLayout()
        self.cf_grid.setSpacing(10)
        cf_lay.addLayout(self.cf_grid)
        self.cf_bar = _ProportionBar()
        cf_lay.addWidget(self.cf_bar)
        cf_lay.addStretch()
        row2.addWidget(cf_box, 1)

        liab_box, liab_lay = _section("Liabilities")
        self.liab_grid = QGridLayout()
        self.liab_grid.setSpacing(10)
        liab_lay.addLayout(self.liab_grid)
        liab_lay.addStretch()
        row2.addWidget(liab_box, 1)
        root.addLayout(row2)

        # ── Goals progress  |  Top holdings / movers ─────────────────────
        row3 = QHBoxLayout()
        row3.setSpacing(16)

        goals_box, self.goals_lay = _section("Goals Progress")
        row3.addWidget(goals_box, 1)

        holds_box, self.holds_lay = _section("Top Holdings & Movers")
        row3.addWidget(holds_box, 1)
        root.addLayout(row3)

        # ── Upcoming dues (30 days) ──────────────────────────────────────
        up_box, self.up_lay = _section("Upcoming — Next 30 Days")
        root.addWidget(up_box)

        root.addStretch(1)

    # ------------------------------------------------------------------ data
    def _on_data_changed(self, topic: str) -> None:
        if topic in self._topics:
            self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty:
            self.refresh()

    def refresh(self) -> None:
        try:
            self._refresh_kpis()
        except Exception:
            pass
        for fn in (self._refresh_trend, self._refresh_allocation, self._refresh_cashflow,
                   self._refresh_liabilities, self._refresh_goals,
                   self._refresh_holdings, self._refresh_upcoming):
            try:
                fn()
            except Exception:
                pass
        self._dirty = False

    def _refresh_kpis(self) -> None:
        bs = self.networth_svc.compute()
        period = date.today().strftime("%Y-%m")
        summary = self.txn_service.summary(
            year=period[:4], month=period[5:7]
        )
        self.kpi_networth.set_value(fmt_inr(bs.net_worth, compact=True))
        self.kpi_assets.set_value(fmt_inr(bs.total_assets, compact=True))
        self.kpi_liab.set_value(fmt_inr(bs.total_liabilities, compact=True))
        self.kpi_cash.set_value(fmt_inr(bs.cash_and_bank, compact=True))
        self.kpi_invested.set_value(fmt_inr(self.invest_svc.total_invested(), compact=True))
        self.kpi_portfolio.set_value(fmt_inr(self.invest_svc.total_portfolio_value(), compact=True))
        self.kpi_income.set_value(fmt_inr(summary.get("income", 0.0), compact=True))
        self.kpi_expense.set_value(fmt_inr(summary.get("expense", 0.0), compact=True))

    def _refresh_trend(self) -> None:
        if not self._trend_plot:
            return
        rows = db.fetch_all(
            "SELECT snapshot_date, total_assets, total_liabilities, net_worth "
            "FROM net_worth_snapshots ORDER BY snapshot_date"
        )
        if not rows:
            self._trend_plot.setVisible(False)
            self._trend_empty.setVisible(True)
            return
        self._trend_plot.setVisible(True)
        self._trend_empty.setVisible(False)
        xs = list(range(len(rows)))
        nw = [r["net_worth"] / 1e5 for r in rows]
        assets = [r["total_assets"] / 1e5 for r in rows]
        liab = [r["total_liabilities"] / 1e5 for r in rows]
        self._nw_curve.setData(xs, nw)
        self._asset_curve.setData(xs, assets)
        self._liab_curve.setData(xs, liab)
        # Date ticks at up to ~6 evenly spaced points
        n = len(rows)
        step = max(1, n // 6)
        ticks = [(i, fmt_date(rows[i]["snapshot_date"], "%b %y")) for i in range(0, n, step)]
        axis = self._trend_plot.getAxis("bottom")
        axis.setTicks([ticks])

    def _refresh_allocation(self) -> None:
        alloc = self.invest_svc.asset_allocation()
        self.alloc_bar.load(alloc, ALLOC_COLOURS, BUCKET_LABELS)
        caps = self.invest_svc.stock_breakdown_by_cap()
        cap_labels = {k: k.replace("_", " ").title() for k in caps}
        self.cap_bar.load(caps, CAP_COLOURS, cap_labels)

    def _clear_layout(self, layout) -> None:
        while layout.count():
            it = layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _refresh_cashflow(self) -> None:
        period = date.today().strftime("%Y-%m")
        s = self.txn_service.summary(year=period[:4], month=period[5:7])
        income = s.get("income", 0.0)
        expense = s.get("expense", 0.0)
        invested = s.get("invested", 0.0)
        net = s.get("net", income - expense - invested)
        self._clear_layout(self.cf_grid)
        cells = [
            ("Income", fmt_inr(income, compact=True), _GREEN),
            ("Expenses", fmt_inr(expense, compact=True), _RED),
            ("Invested", fmt_inr(invested, compact=True), "#93c5fd"),
            ("Net", ("+" if net >= 0 else "") + fmt_inr(net, compact=True),
             _GREEN if net >= 0 else _RED),
        ]
        for i, (lbl, val, col) in enumerate(cells):
            self.cf_grid.addWidget(_kv(lbl, val, col), i // 2, i % 2)
        self.cf_bar.load(
            {"income": income, "expense": expense, "invested": max(0.0, invested)},
            {"income": _GREEN, "expense": _RED, "invested": "#93c5fd"},
            {"income": "Income", "expense": "Expenses", "invested": "Invested"},
        )

    def _refresh_liabilities(self) -> None:
        from utils.calculators import emi as calc_emi
        liabs = self.ctx.liability_service.list_active()
        total_out = sum(lb.outstanding for lb in liabs)
        total_emi = 0.0
        weighted = 0.0
        for lb in liabs:
            emi_val = lb.emi_amount or (
                calc_emi(lb.outstanding, (lb.interest_rate or 0) / 100, lb.remaining_months)
                if lb.remaining_months and lb.interest_rate else 0
            )
            total_emi += emi_val
            weighted += (lb.interest_rate or 0) * lb.outstanding
        avg_rate = (weighted / total_out) if total_out > 0 else 0.0
        self._clear_layout(self.liab_grid)
        cells = [
            ("Outstanding", fmt_inr(total_out, compact=True), _RED),
            ("EMI / Month", fmt_inr(total_emi, compact=True), _AMBER),
            ("Avg Rate", fmt_pct(avg_rate), ""),
            ("Count", str(len(liabs)), ""),
        ]
        for i, (lbl, val, col) in enumerate(cells):
            self.liab_grid.addWidget(_kv(lbl, val, col), i // 2, i % 2)

    def _refresh_goals(self) -> None:
        self._clear_layout(self.goals_lay)
        goals = self.ctx.goal_service.list_active()
        if not goals:
            lbl = QLabel("No active goals.")
            lbl.setStyleSheet("color:#9c8869; background:transparent;")
            self.goals_lay.addWidget(lbl)
            return
        for g in goals[:6]:
            row = QWidget()
            rl = QVBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(2)
            sip = self.projection_svc.required_sip_for_goal(g)
            head = QLabel(
                f"{g.name}  —  {fmt_inr(g.current_amount, compact=True)} / "
                f"{fmt_inr(g.target_amount, compact=True)}"
                + (f"   ·   SIP {fmt_inr(sip, compact=True)}/mo" if sip > 0 else "")
            )
            head.setStyleSheet("color:#e7e0d4; font-size:12px; background:transparent;")
            rl.addWidget(head)
            pct = int(g.progress_pct)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(max(0, min(100, pct)))
            bar.setFixedHeight(14)
            bar.setFormat("%p%")
            colour = "#16a34a" if pct >= 100 else "#f59e0b" if pct >= 50 else "#3b82f6"
            bar.setStyleSheet(
                "QProgressBar{background:rgba(201,170,122,0.12); border:none; "
                "border-radius:5px; color:#e7e0d4; font-size:9px;}"
                f"QProgressBar::chunk{{background:{colour}; border-radius:5px;}}"
            )
            rl.addWidget(bar)
            self.goals_lay.addWidget(row)
        self.goals_lay.addStretch()

    def _refresh_holdings(self) -> None:
        self._clear_layout(self.holds_lay)
        holdings = self.invest_svc.list_active()
        if not holdings:
            lbl = QLabel("No holdings yet.")
            lbl.setStyleSheet("color:#9c8869; background:transparent;")
            self.holds_lay.addWidget(lbl)
            return

        def _hdr(text: str) -> None:
            h = QLabel(text)
            h.setObjectName("kpiTitle")
            self.holds_lay.addWidget(h)

        def _line(name: str, right: str, colour: str = "#e7e0d4") -> None:
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            n = QLabel(name)
            n.setStyleSheet("color:#e7e0d4; font-size:12px; background:transparent;")
            r = QLabel(right)
            r.setStyleSheet(f"color:{colour}; font-size:12px; font-weight:600; background:transparent;")
            hl.addWidget(n, 1)
            hl.addWidget(r, 0)
            self.holds_lay.addWidget(w)

        top = sorted(holdings, key=lambda h: h.current_value, reverse=True)[:5]
        _hdr("Largest holdings")
        for h in top:
            _line(h.name, fmt_inr(h.current_value, compact=True))

        movers = sorted(holdings, key=lambda h: h.return_pct, reverse=True)
        best = movers[0]
        worst = movers[-1]
        _hdr("Movers")
        _line(f"Best · {best.name}", ("+" if best.return_pct >= 0 else "") + fmt_pct(best.return_pct),
              _GREEN if best.return_pct >= 0 else _RED)
        if worst.id != best.id:
            _line(f"Worst · {worst.name}", ("+" if worst.return_pct >= 0 else "") + fmt_pct(worst.return_pct),
                  _GREEN if worst.return_pct >= 0 else _RED)
        self.holds_lay.addStretch()

    def _refresh_upcoming(self) -> None:
        self._clear_layout(self.up_lay)
        today = date.today()
        horizon = today.toordinal() + 30
        items: list[tuple[str, str, str]] = []  # (when, what, amount)

        def _within(d: Optional[str]) -> bool:
            if not d:
                return False
            try:
                return today.toordinal() <= date.fromisoformat(d).toordinal() <= horizon
            except ValueError:
                return False

        # Liability EMIs / dues
        for lb in self.ctx.liability_service.list_active():
            if _within(lb.next_due_date):
                items.append((lb.next_due_date, f"EMI · {lb.name}",
                              fmt_inr(lb.emi_amount, compact=True) if lb.emi_amount else ""))

        # FD maturities & insurance premiums
        try:
            for h in self.invest_svc.upcoming_maturities(within_days=30):
                when = h.maturity_date or h.premium_due_date or ""
                what = ("Maturity · " if h.maturity_date else "Premium · ") + h.name
                amt = fmt_inr(h.premium_amount, compact=True) if h.premium_amount else ""
                items.append((when, what, amt))
        except Exception:
            pass

        # Standalone reminders table
        try:
            for r in db.fetch_all(
                "SELECT title, due_date, amount FROM reminders "
                "WHERE COALESCE(is_done,0)=0 ORDER BY due_date"
            ):
                if _within(r["due_date"]):
                    items.append((r["due_date"], r["title"],
                                  fmt_inr(r["amount"], compact=True) if r["amount"] else ""))
        except Exception:
            pass

        # Pending income this month
        period = today.strftime("%Y-%m")
        for s in self.income_svc.pending_sources(
            self.ctx.income_source_service.list_active(), period
        ):
            items.append((f"{period}-28", f"Income due · {s.name}",
                          fmt_inr(self.ctx.income_source_service.net_monthly(s), compact=True)))

        if not items:
            lbl = QLabel("Nothing due in the next 30 days.")
            lbl.setStyleSheet("color:#9c8869; background:transparent;")
            self.up_lay.addWidget(lbl)
            return

        for when, what, amount in sorted(items, key=lambda x: x[0]):
            w = QWidget()
            hl = QHBoxLayout(w)
            hl.setContentsMargins(0, 0, 0, 0)
            d_lbl = QLabel(fmt_date(when))
            d_lbl.setStyleSheet("color:#c4a878; font-size:12px; background:transparent;")
            d_lbl.setFixedWidth(110)
            what_lbl = QLabel(what)
            what_lbl.setStyleSheet("color:#e7e0d4; font-size:12px; background:transparent;")
            amt_lbl = QLabel(amount)
            amt_lbl.setStyleSheet("color:#fbbf24; font-size:12px; font-weight:600; background:transparent;")
            hl.addWidget(d_lbl, 0)
            hl.addWidget(what_lbl, 1)
            hl.addWidget(amt_lbl, 0)
            self.up_lay.addWidget(w)
