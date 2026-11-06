"""Projections - where the current path leads.

Left: Net worth plus one tile per goal. Right: the selected projection.
Assumptions are saved (Preferences) and every change recalculates.

Numbers and tables only - no charts here, by design.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.app_context import AppContext
from services.projection_service import Assumptions, Stress
from ui.theme import theme
from ui.widgets.common import Banner, Card, EmptyState, PageHeader, StatGrid, clear_layout, label
from ui.widgets.list_tile import ListTile
from utils.formatters import fmt_date, fmt_inr
from utils.logger import get_logger

log = get_logger(__name__)


def _c(v: float) -> str:
    return fmt_inr(v, compact=True)


def _pct_spin(value: float, lo: float = -20.0, hi: float = 50.0) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(1)
    s.setSingleStep(0.5)
    s.setSuffix(" %")
    s.setValue(value)
    return s


def _int_spin(value: int, lo: int, hi: int, suffix: str = "") -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(value)
    if suffix:
        s.setSuffix(suffix)
    return s


def _section(title: str) -> tuple[QWidget, QVBoxLayout]:
    holder = QWidget()
    lay = QVBoxLayout(holder)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(10)
    lay.addWidget(label(title, "sectionTitle"))
    return holder, lay


class ProjectionsView(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._topics = {"accounts", "transactions", "income_sources", "income_entries",
                        "holdings", "liabilities", "goals", "goal_holdings", "fx_rates"}
        self._dirty = True
        self.svc = ctx.projection_service
        self._baseline = None
        self._assumptions: Optional[Assumptions] = None
        self._proj: list = []
        self._stress_proj: Optional[list] = None
        self._tiles: list[ListTile] = []
        self._selected_key: str = "networth"
        self._goal_forecasts: dict = {}
        self._loading = True

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._recompute)

        self.ctx.events.changed.connect(self._on_data_changed)
        self._build()
        self._loading = False
        self._recompute()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(18)
        root.addWidget(PageHeader(
            "Projections",
            "Where your current path leads. Change an assumption and everything recalculates."))

        saved = self.ctx.preferences.get("projection") or {}
        a_card = Card("Your assumptions", padding=16, spacing=10)
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.s_age = _int_spin(int(saved.get("current_age", 30)), 18, 90, " yrs")
        self.s_retire = _int_spin(int(saved.get("retirement_age", 60)), 30, 85, " yrs")
        self.s_life = _int_spin(int(saved.get("life_expectancy", 85)), 60, 110, " yrs")
        self.s_horizon = _int_spin(int(saved.get("horizon_years", 30)), 1, 70, " yrs")
        self.s_return = _pct_spin(float(saved.get("expected_return", 10.0)))
        self.s_post = _pct_spin(float(saved.get("post_retire_return", 7.0)))
        self.s_inf = _pct_spin(float(saved.get("inflation", 6.0)))
        self.s_salary = _pct_spin(float(saved.get("salary_growth", 8.0)))
        self.s_expense = _pct_spin(float(saved.get("expense_growth", 6.0)))
        fields = [
            ("Your age", self.s_age), ("Retire at", self.s_retire), ("Plan until age", self.s_life),
            ("Project for", self.s_horizon), ("Return while working", self.s_return),
            ("Return after retiring", self.s_post), ("Inflation", self.s_inf),
            ("Income growth", self.s_salary), ("Spending growth", self.s_expense),
        ]
        for i, (text, w) in enumerate(fields):
            r, c = divmod(i, 5)
            cell = QVBoxLayout()
            cell.setSpacing(4)
            cell.addWidget(label(text, "statLabel"))
            cell.addWidget(w)
            grid.addLayout(cell, r, c)
            w.valueChanged.connect(self._schedule)
        a_card.body.addLayout(grid)

        stress = QHBoxLayout()
        stress.setSpacing(10)
        self.s_stress = QCheckBox("Stress test: what if returns are lower and income stops for a while?")
        self.s_stress_drop = _pct_spin(3.0, 0.0, 10.0)
        self.s_stress_shock = _int_spin(1, 0, 10, " yrs")
        self.s_stress.toggled.connect(self._schedule)
        self.s_stress_drop.valueChanged.connect(self._schedule)
        self.s_stress_shock.valueChanged.connect(self._schedule)
        stress.addWidget(self.s_stress)
        stress.addSpacing(8)
        stress.addWidget(label("returns lower by", "small"))
        stress.addWidget(self.s_stress_drop)
        stress.addWidget(label("no income for", "small"))
        stress.addWidget(self.s_stress_shock)
        stress.addStretch(1)
        a_card.body.addLayout(stress)
        root.addWidget(a_card)

        self.banner_box = QVBoxLayout()
        root.addLayout(self.banner_box)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tile_container = QWidget()
        self.tile_layout = QVBoxLayout(self.tile_container)
        self.tile_layout.setContentsMargins(0, 0, 8, 0)
        self.tile_layout.setSpacing(8)
        self.tile_layout.addStretch(1)
        self.scroll.setWidget(self.tile_container)
        self.scroll.setMinimumWidth(300)
        splitter.addWidget(self.scroll)

        card = QFrame()
        card.setObjectName("detailCard")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        self.detail_stack = QStackedWidget()
        self.detail_stack.addWidget(EmptyState("projections", "Nothing to project yet",
                                               "Add accounts, income and investments first."))
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.detail_host = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_host)
        self.detail_layout.setContentsMargins(20, 18, 20, 18)
        self.detail_layout.setSpacing(20)
        self.detail_scroll.setWidget(self.detail_host)
        self.detail_stack.addWidget(self.detail_scroll)
        card_lay.addWidget(self.detail_stack)
        splitter.addWidget(card)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 7)
        splitter.setSizes([360, 640])
        root.addWidget(splitter, 1)

    # -------------------------------------------------------------- compute
    def _schedule(self, *_args) -> None:
        if not self._loading:
            self._debounce.start()

    def _assumptions_from_form(self) -> Assumptions:
        return Assumptions(
            current_age=self.s_age.value(),
            retirement_age=self.s_retire.value(),
            life_expectancy=self.s_life.value(),
            horizon_years=self.s_horizon.value(),
            expected_return=self.s_return.value() / 100.0,
            post_retire_return=self.s_post.value() / 100.0,
            inflation=self.s_inf.value() / 100.0,
            salary_growth=self.s_salary.value() / 100.0,
            expense_growth=self.s_expense.value() / 100.0,
        )

    def _save_assumptions(self) -> None:
        self.ctx.preferences.set("projection", {
            "current_age": self.s_age.value(), "retirement_age": self.s_retire.value(),
            "life_expectancy": self.s_life.value(), "horizon_years": self.s_horizon.value(),
            "expected_return": self.s_return.value(), "post_retire_return": self.s_post.value(),
            "inflation": self.s_inf.value(), "salary_growth": self.s_salary.value(),
            "expense_growth": self.s_expense.value(),
        })

    def _on_data_changed(self, topic: str) -> None:
        if topic in self._topics:
            self._dirty = True

    def mark_dirty(self) -> None:
        self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty:
            self._recompute()

    def refresh(self) -> None:
        self._recompute()

    def _recompute(self) -> None:
        try:
            self._baseline = self.ctx.derive_projection_baseline()
        except Exception:
            log.exception("Projection baseline failed")
            return
        self._assumptions = self._assumptions_from_form()
        if not self._loading:
            self._save_assumptions()
        try:
            self._proj = self.svc.project_long_term(self._baseline, self._assumptions)
        except Exception:
            log.exception("Projection failed")
            self._proj = []
        self._stress_proj = None
        if self.s_stress.isChecked():
            try:
                self._stress_proj = self.svc.project_long_term(
                    self._baseline, self._assumptions,
                    Stress(return_drop=self.s_stress_drop.value() / 100.0,
                           income_shock_years=self.s_stress_shock.value()))
            except Exception:
                log.exception("Stress projection failed")
        self._refresh_banners()
        self._refresh_tiles()
        self._render_detail()
        self._dirty = False

    def _refresh_banners(self) -> None:
        clear_layout(self.banner_box)
        b = self._baseline
        if b is None:
            return
        if b.monthly_expenses <= 0:
            self.banner_box.addWidget(Banner(
                "No spending recorded in the last six months, so these projections assume you "
                "spend nothing. Log your expenses for a realistic picture.", "warning"))
        elif b.monthly_net_income > 0 and b.monthly_expenses < 0.15 * b.monthly_net_income:
            self.banner_box.addWidget(Banner(
                f"Only {_c(b.monthly_expenses)} a month of spending was recorded over the last six "
                f"months, against {_c(b.monthly_net_income)} take-home - so these projections are "
                "probably optimistic. Log your expenses for a realistic picture.", "warning"))

    # ---------------------------------------------------------------- tiles
    def _refresh_tiles(self) -> None:
        for t in self._tiles:
            t.setParent(None)
            t.deleteLater()
        self._tiles = []
        while self.tile_layout.count():
            self.tile_layout.takeAt(0)

        if self._baseline is not None and self._proj:
            last = self._proj[-1]
            plan = self.svc.retirement_plan(self._baseline, self._assumptions)
            runs_out = self.svc.depletion_age(self._proj)
            if runs_out is not None:
                chip = (f"Runs out at {runs_out}", "negative")
            elif plan.on_track:
                chip = ("On track", "positive")
            else:
                chip = (f"Short {_c(plan.gap)}", "warning")
            self._add_tile(ListTile(
                "networth", "Net worth",
                f"Today {_c(self._baseline.net_worth)} · {_c(last.net_worth_real)} in today's money",
                value=f"{_c(last.net_worth_nominal)} at {last.age}", chip=chip,
                icon_name="projections", selected=self._selected_key == "networth"))

        forecasts = self.ctx.goal_projection_forecasts()
        self._goal_forecasts = {f.goal.id: f for f in forecasts}
        for f in forecasts:
            if f.target_date and f.on_track_months is None:
                chip = ("No SIP linked", "warning")
            elif f.target_date:
                chip = ("On track", "positive") if f.will_meet_target else ("Behind", "negative")
            else:
                chip = ("No date", "neutral")
            sub = f"{_c(f.funded)} of {_c(f.target)}"
            if f.target_date:
                sub += f" · by {fmt_date(f.target_date, '%b %Y')}"
            value = (f"{_c(f.required_sip)}/mo" if f.required_sip > 0
                     else f"{_c(f.estimated_current_sip)}/mo in")
            key = f"goal:{f.goal.id}"
            self._add_tile(ListTile(key, f.goal.name or "Goal", sub, value=value, chip=chip,
                                    icon_name="goals", selected=self._selected_key == key))
        self.tile_layout.addStretch(1)

    def _add_tile(self, tile: ListTile) -> None:
        tile.clicked.connect(self._on_tile_clicked)
        self._tiles.append(tile)
        self.tile_layout.addWidget(tile)

    def _on_tile_clicked(self, key: str) -> None:
        self._selected_key = key
        for t in self._tiles:
            t.set_selected(t.key == key)
        self._render_detail()

    # --------------------------------------------------------------- detail
    def _render_detail(self) -> None:
        clear_layout(self.detail_layout)
        if not self._tiles:
            self.detail_stack.setCurrentIndex(0)
            return
        if self._selected_key not in {t.key for t in self._tiles}:
            self._selected_key = self._tiles[0].key
            for t in self._tiles:
                t.set_selected(t.key == self._selected_key)
        self.detail_stack.setCurrentIndex(1)
        try:
            if self._selected_key == "networth":
                self._render_networth()
            elif self._selected_key.startswith("goal:"):
                f = self._goal_forecasts.get(int(self._selected_key.split(":", 1)[1]))
                if f is not None:
                    self._render_goal(f)
        except Exception:
            log.exception("Projection detail failed")
        self.detail_layout.addStretch(1)

    def _render_networth(self) -> None:
        if not (self._baseline and self._proj and self._assumptions):
            return
        a, b, proj = self._assumptions, self._baseline, self._proj
        self.detail_layout.addWidget(label("Net worth", "detailTitle"))

        retire_idx = max(0, min(a.retirement_age - a.current_age, len(proj) - 1))
        runs_out = self.svc.depletion_age(proj)
        top = StatGrid(3)
        top.set_items([
            ("Today", _c(b.net_worth)),
            (f"At retirement (age {proj[retire_idx].age})", _c(proj[retire_idx].net_worth_nominal)),
            (f"At age {proj[-1].age}", _c(proj[-1].net_worth_nominal)),
            ("Same, in today's money", _c(proj[-1].net_worth_real)),
            ("Monthly spending used", _c(b.monthly_expenses), None if b.monthly_expenses else "warning"),
            ("Money lasts", f"Runs out at age {runs_out}" if runs_out else f"Beyond age {proj[-1].age}",
             "negative" if runs_out else "positive"),
        ])
        self.detail_layout.addWidget(top)
        if runs_out:
            self.detail_layout.addWidget(Banner(
                f"On these assumptions your savings run out at age {runs_out}: spending is paid "
                "from cash and then investments once income stops.", "negative"))

        holder, lay = _section("Year by year")
        stress = {p.year: p for p in (self._stress_proj or [])}
        cols = ["Age", "Net worth", "Today's money", "Investments", "Cash flow"]
        if self._stress_proj:
            cols.append("Stress test")
        years_to_retire = max(0, a.retirement_age - a.current_age)
        picks = sorted({0, 1, 5, 10, 15, 20, years_to_retire, 25, 30, 40, a.horizon_years}
                       | ({runs_out - a.current_age} if runs_out else set()))
        picks = [y for y in picks if 0 <= y < len(proj)]
        table = QTableWidget(len(picks), len(cols))
        table.setHorizontalHeaderLabels(cols)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34)
        table.setShowGrid(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hh = table.horizontalHeader()
        for c in range(len(cols)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)
        right = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        for r, y in enumerate(picks):
            p = proj[y]
            cash_flow = p.savings
            cells = [str(p.age) + (" · retire" if y == years_to_retire and y else ""),
                     _c(p.net_worth_nominal), _c(p.net_worth_real), _c(p.portfolio_value),
                     ("+" if cash_flow >= 0 else "−") + _c(abs(cash_flow))]
            if self._stress_proj:
                sp = stress.get(y)
                cells.append(_c(sp.net_worth_nominal) if sp else "-")
            for c, text in enumerate(cells):
                it = QTableWidgetItem(text)
                if c:
                    it.setTextAlignment(right)
                if c == 4 and cash_flow < 0:
                    it.setForeground(theme.qcolor("negative"))
                if p.shortfall > 0.5 and c in (1, 3):
                    it.setForeground(theme.qcolor("negative"))
                table.setItem(r, c, it)
        table.setMinimumHeight(40 + 34 * len(picks))
        lay.addWidget(table)
        lay.addWidget(label("Cash flow = take-home income − spending − EMIs. Surplus is invested; "
                            "a deficit is paid from cash, then investments.", "small", wrap=True))
        self.detail_layout.addWidget(holder)

        plan = self.svc.retirement_plan(b, a)
        holder, lay = _section("Retirement")
        grid = StatGrid(3)
        grid.set_items([
            ("Years to go", str(plan.years_to_retirement)),
            ("Spending today (yearly)", _c(plan.annual_expenses_today)),
            ("Spending at retirement", _c(plan.annual_expenses_at_retirement)),
            ("Corpus needed", _c(plan.corpus_needed)),
            ("Corpus projected", _c(plan.corpus_projected), "positive" if plan.on_track else None),
            ("Extra SIP to close the gap", _c(plan.required_additional_sip) + "/mo",
             "warning" if plan.required_additional_sip > 0 else "positive"),
        ])
        lay.addWidget(grid)
        if plan.on_track:
            lay.addWidget(Banner("On track for retirement on the current path.", "positive"))
        else:
            lay.addWidget(Banner(
                f"Short by {_c(plan.gap)}. Investing an extra {_c(plan.required_additional_sip)} a "
                f"month for {plan.years_to_retirement} years closes the gap.", "warning"))
        self.detail_layout.addWidget(holder)

    def _render_goal(self, f) -> None:
        g = f.goal
        self.detail_layout.addWidget(label(g.name or "Goal", "detailTitle"))
        grid = StatGrid(3)
        grid.set_items([
            ("Target", _c(f.target)),
            ("Saved", _c(f.funded), "positive"),
            ("Still needed", _c(max(0.0, f.target - f.funded)),
             "negative" if f.target > f.funded else "positive"),
            ("Target date", fmt_date(f.target_date) if f.target_date else "-"),
            ("Reached at current pace", fmt_date(f.on_track_date) if f.on_track_date else "-",
             "positive" if f.will_meet_target else "warning"),
            ("Months to target", str(f.months_to_target) if f.months_to_target else "-"),
            ("Needed per month", _c(f.required_sip), "accent"),
            ("Going in per month", _c(f.estimated_current_sip)),
            ("Expected return", f"{(g.expected_return or 0.10) * 100:.1f}%"),
        ])
        self.detail_layout.addWidget(grid)

        if f.target_date and f.on_track_months is not None:
            if f.will_meet_target:
                self.detail_layout.addWidget(Banner(
                    f"You'll reach this by {fmt_date(f.on_track_date)} at "
                    f"{_c(f.estimated_current_sip)} a month.", "positive"))
            else:
                self.detail_layout.addWidget(Banner(
                    f"Behind. Investing {_c(f.required_sip)} a month would reach it by "
                    f"{fmt_date(f.target_date)}.", "negative"))
        elif f.target_date and f.estimated_current_sip == 0:
            self.detail_layout.addWidget(Banner(
                "No SIP linked to this goal. Link the investments that fund it "
                "(Goals → Edit → Funded by) to project progress.", "warning"))
        else:
            self.detail_layout.addWidget(Banner("Set a target date to check feasibility.", "info"))

        ids = self.ctx.goal_linked_holding_ids(g.id)
        holdings = self.ctx.holdings_by_id()
        rows = [holdings[i] for i in ids if i in holdings]
        if rows:
            holder, lay = _section("Funded by")
            for h in rows:
                line = QHBoxLayout()
                line.addWidget(label(h.name, "rowTitle"), 1)
                bits = [f"SIP {_c(h.sip_amount)}/mo"] if h.sip_amount else []
                bits.append(f"Value {_c(h.current_value)}")
                line.addWidget(label("  ·  ".join(bits), "rowMeta"))
                lay.addLayout(line)
            self.detail_layout.addWidget(holder)

