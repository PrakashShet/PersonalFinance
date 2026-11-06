"""Projections tab — tile-based master/detail.

Top: a compact Assumptions panel with a "Recalculate" button.
Left: tiles for Net Worth (long-range) and each active Goal.
Right: a detail pane with the projection breakdown for the selected tile.

No charts — projection data is shown as numbers and tables/lists, per spec.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from services.app_context import AppContext
from services.projection_service import Assumptions, Stress
from ui.widgets.projection_tile import ProjectionTile
from utils.formatters import fmt_inr, fmt_date

_C_OK   = "#6ee7b7"
_C_WARN = "#fbbf24"
_C_BAD  = "#fca5a5"
_C_INFO = "#93c5fd"
_C_MUTE = "#9c8869"


# ── small helpers ───────────────────────────────────────────────────────────


def _section(title: str) -> tuple[QGroupBox, QVBoxLayout]:
    box = QGroupBox(title)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(8)
    return box, lay


class _CollapsibleSection(QFrame):
    """Section with a clickable header that shows/hides its content."""

    _STYLE = """
    QFrame#collapsibleSection {
        background-color: rgba(201, 170, 122, 0.06);
        border: 1px solid rgba(201, 170, 122, 0.25);
        border-radius: 10px;
    }
    QToolButton#sectionToggle {
        background: transparent;
        border: none;
        color: #c4a878;
        font-weight: 700;
        font-size: 13px;
        padding: 10px 14px;
        text-align: left;
    }
    QToolButton#sectionToggle:hover { color: #f3ecdf; }
    """

    def __init__(self, title: str, start_expanded: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("collapsibleSection")
        self.setStyleSheet(self._STYLE)
        self._title = title

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._toggle = QToolButton()
        self._toggle.setObjectName("sectionToggle")
        self._toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(start_expanded)
        self._toggle.setSizePolicy(self._toggle.sizePolicy().horizontalPolicy(),
                                   self._toggle.sizePolicy().verticalPolicy())
        self._toggle.toggled.connect(self._on_toggled)
        outer.addWidget(self._toggle)

        self._content = QWidget()
        self.content_layout = QVBoxLayout(self._content)
        self.content_layout.setContentsMargins(14, 4, 14, 12)
        self.content_layout.setSpacing(8)
        outer.addWidget(self._content)

        self._content.setVisible(start_expanded)
        self._refresh_label()

    def _on_toggled(self, expanded: bool) -> None:
        self._content.setVisible(expanded)
        self._refresh_label()

    def _refresh_label(self) -> None:
        arrow = "▼" if self._toggle.isChecked() else "▶"
        self._toggle.setText(f"{arrow}  {self._title}")


def _kv(label: str, value: str, colour: str = "") -> QWidget:
    w = QWidget(); v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0); v.setSpacing(2)
    t = QLabel(label); t.setObjectName("kpiTitle")
    val = QLabel(value)
    style = "font-size:16px; font-weight:700; background:transparent;"
    if colour: style += f" color:{colour};"
    val.setStyleSheet(style)
    v.addWidget(t); v.addWidget(val)
    return w


def _pct_spin(default: float, max_val: float = 50.0) -> QDoubleSpinBox:
    s = QDoubleSpinBox(); s.setRange(-20, max_val); s.setDecimals(2); s.setSuffix(" %")
    s.setValue(default); return s


def _int_spin(default: int, min_val: int = 0, max_val: int = 120) -> QSpinBox:
    s = QSpinBox(); s.setRange(min_val, max_val); s.setValue(default); return s


# ── view ────────────────────────────────────────────────────────────────────


class ProjectionsView(QWidget):
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
        self.networth_svc = ctx.net_worth_service
        self.income_svc = ctx.income_service
        self.svc = ctx.projection_service

        # State
        self._baseline = None
        self._assumptions: Optional[Assumptions] = None
        self._proj: list = []
        self._stress_proj: Optional[list] = None
        self._tiles: list[ProjectionTile] = []
        self._selected_key: str = "networth"

        self.ctx.events.changed.connect(self._on_data_changed)
        self._build()
        self._recompute()

    # ── build ────────────────────────────────────────────────────────────
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        title = QLabel("Projections"); title.setObjectName("pageTitle")
        root.addWidget(title)

        # Assumptions (collapsible)
        a_box = _CollapsibleSection("Assumptions", start_expanded=True)
        a_lay = a_box.content_layout
        form = QFormLayout(); form.setHorizontalSpacing(20); form.setVerticalSpacing(6)
        self.s_age     = _int_spin(30, 18, 90)
        self.s_retire  = _int_spin(60, 30, 80)
        self.s_life    = _int_spin(85, 60, 120)
        self.s_horizon = _int_spin(30, 1, 60)
        self.s_return  = _pct_spin(10.0)
        self.s_post    = _pct_spin(7.0)
        self.s_inf     = _pct_spin(6.0)
        self.s_salary  = _pct_spin(8.0)
        self.s_expense = _pct_spin(6.0)
        form.addRow("Current age", self.s_age)
        form.addRow("Retirement age", self.s_retire)
        form.addRow("Life expectancy", self.s_life)
        form.addRow("Horizon (yrs)", self.s_horizon)
        form.addRow("Expected return", self.s_return)
        form.addRow("Post-retire return", self.s_post)
        form.addRow("Inflation", self.s_inf)
        form.addRow("Salary growth", self.s_salary)
        form.addRow("Expense growth", self.s_expense)
        a_lay.addLayout(form)

        bar = QHBoxLayout()
        self.s_stress       = QCheckBox("Stress test")
        self.s_stress_drop  = _pct_spin(3.0, max_val=10.0)
        self.s_stress_shock = _int_spin(1, 0, 10)
        bar.addWidget(self.s_stress)
        bar.addSpacing(10); bar.addWidget(QLabel("Return drop:")); bar.addWidget(self.s_stress_drop)
        bar.addSpacing(10); bar.addWidget(QLabel("Income shock yrs:")); bar.addWidget(self.s_stress_shock)
        bar.addStretch()
        recalc = QPushButton("Recalculate"); recalc.setObjectName("primaryBtn")
        recalc.clicked.connect(self._recompute)
        bar.addWidget(recalc)
        a_lay.addLayout(bar)
        root.addWidget(a_box)

        # Splitter: tiles | detail
        splitter = QSplitter(Qt.Orientation.Horizontal); splitter.setChildrenCollapsible(False)

        # Left: scrollable tile list
        left = QWidget(); ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(6)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tile_container = QWidget()
        self.tile_layout = QVBoxLayout(self.tile_container)
        self.tile_layout.setContentsMargins(0, 4, 6, 4); self.tile_layout.setSpacing(10)
        self.tile_layout.addStretch(1)
        self.scroll.setWidget(self.tile_container)
        self.scroll.setMinimumWidth(320)
        ll.addWidget(self.scroll, 1)
        splitter.addWidget(left)

        # Right: stacked detail (placeholder + dynamic content)
        self.detail_stack = QStackedWidget()
        placeholder = QLabel("Select a projection on the left to see details.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setObjectName("tileFlags")
        self.detail_stack.addWidget(placeholder)

        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        self.detail_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.detail_host = QWidget()
        self.detail_layout = QVBoxLayout(self.detail_host)
        self.detail_layout.setContentsMargins(8, 4, 8, 4); self.detail_layout.setSpacing(12)
        self.detail_scroll.setWidget(self.detail_host)
        self.detail_stack.addWidget(self.detail_scroll)

        splitter.addWidget(self.detail_stack)
        splitter.setSizes([420, 620])
        root.addWidget(splitter, 1)

    # ── recompute ────────────────────────────────────────────────────────
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

    def _on_data_changed(self, topic: str) -> None:
        if topic in self._topics:
            self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty:
            self._recompute()

    def _recompute(self) -> None:
        try:
            self._baseline = self.ctx.derive_projection_baseline()
        except Exception:
            return
        self._assumptions = self._assumptions_from_form()
        try:
            self._proj = self.svc.project_long_term(self._baseline, self._assumptions)
        except Exception:
            self._proj = []
        self._stress_proj = None
        if self.s_stress.isChecked():
            try:
                self._stress_proj = self.svc.project_long_term(
                    self._baseline, self._assumptions,
                    Stress(return_drop=self.s_stress_drop.value() / 100.0,
                           income_shock_years=self.s_stress_shock.value()),
                )
            except Exception:
                self._stress_proj = None
        self._refresh_tiles()
        self._render_detail()
        self._dirty = False

    # ── tiles ────────────────────────────────────────────────────────────
    def _refresh_tiles(self) -> None:
        # Tear down existing tiles
        for t in self._tiles:
            self.tile_layout.removeWidget(t); t.deleteLater()
        self._tiles = []
        while self.tile_layout.count():
            self.tile_layout.takeAt(0)

        # Net Worth tile
        if self._baseline and self._proj:
            last = self._proj[-1]
            plan = self.svc.retirement_plan(self._baseline, self._assumptions)
            if plan.on_track:
                status, kind = "On track", "ok"
            else:
                status, kind = f"Short {fmt_inr(plan.gap, compact=True)}", "warn"
            t = ProjectionTile(
                key="networth",
                title="Net Worth",
                subtitle=(f"Today {fmt_inr(self._baseline.net_worth, compact=True)}"
                          f"   →   Yr {last.year} {fmt_inr(last.net_worth_nominal, compact=True)}"),
                value_text=(f"Real (today's rupees): "
                            f"{fmt_inr(last.net_worth_real, compact=True)}"),
                status_text=status, status_kind=kind,
                selected=(self._selected_key == "networth"),
                on_click=self._on_tile_clicked,
                parent=self.tile_container,
            )
            self._tiles.append(t); self.tile_layout.addWidget(t)

        # Per-goal tiles
        forecasts = self.ctx.goal_projection_forecasts()
        if forecasts:
            self._goal_forecasts = {f.goal.id: f for f in forecasts}
            for f in forecasts:
                if f.target_date and f.on_track_months is None:
                    status, kind = "No funding", "bad"
                elif f.target_date and f.on_track_months is not None:
                    status, kind = ("On track", "ok") if f.will_meet_target else ("Behind", "bad")
                else:
                    status, kind = "No target", "info"
                subtitle = (
                    f"Funded {fmt_inr(f.funded, compact=True)} of "
                    f"{fmt_inr(f.target, compact=True)}"
                )
                if f.on_track_date:
                    subtitle += f"   ·   on-track {fmt_date(f.on_track_date)}"
                elif f.target_date:
                    subtitle += f"   ·   target {fmt_date(f.target_date)}"
                value = (
                    f"Required SIP: {fmt_inr(f.required_sip, compact=True)} / mo"
                    if f.required_sip > 0
                    else f"Current SIP: {fmt_inr(f.estimated_current_sip, compact=True)} / mo"
                )
                tile = ProjectionTile(
                    key=f"goal:{f.goal.id}",
                    title=f.goal.name or "Goal",
                    subtitle=subtitle,
                    value_text=value,
                    status_text=status, status_kind=kind,
                    selected=(self._selected_key == f"goal:{f.goal.id}"),
                    on_click=self._on_tile_clicked,
                    parent=self.tile_container,
                )
                self._tiles.append(tile); self.tile_layout.addWidget(tile)
        else:
            self._goal_forecasts = {}
        self.tile_layout.addStretch(1)

    def _on_tile_clicked(self, key: str) -> None:
        self._selected_key = key
        for t in self._tiles:
            t.set_selected(t.key == key)
        self._render_detail()

    # ── detail rendering ─────────────────────────────────────────────────
    def _clear_layout(self, layout) -> None:
        while layout.count():
            it = layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _render_detail(self) -> None:
        self._clear_layout(self.detail_layout)
        if not self._tiles:
            self.detail_stack.setCurrentIndex(0); return
        # Ensure a default selection if the previous key disappeared
        if self._selected_key not in {t.key for t in self._tiles}:
            self._selected_key = self._tiles[0].key
            for t in self._tiles:
                t.set_selected(t.key == self._selected_key)

        self.detail_stack.setCurrentIndex(1)
        if self._selected_key == "networth":
            self._render_networth_detail()
        elif self._selected_key.startswith("goal:"):
            gid = int(self._selected_key.split(":", 1)[1])
            f = self._goal_forecasts.get(gid)
            if f is not None:
                self._render_goal_detail(f)

    # Net-worth detail: assumptions snapshot, milestones table, retirement
    def _render_networth_detail(self) -> None:
        if not (self._baseline and self._proj and self._assumptions):
            return
        a = self._assumptions

        # --- Assumptions summary ---
        as_box, as_lay = _section("Assumptions in use")
        grid = QGridLayout(); grid.setSpacing(10)
        cells = [
            ("Age now → retire", f"{a.current_age} → {a.retirement_age}", ""),
            ("Horizon",          f"{a.horizon_years} yrs", ""),
            ("Return",           f"{a.expected_return * 100:.1f}%", _C_INFO),
            ("Inflation",        f"{a.inflation * 100:.1f}%", _C_WARN),
            ("Salary growth",    f"{a.salary_growth * 100:.1f}%", ""),
            ("Expense growth",   f"{a.expense_growth * 100:.1f}%", ""),
        ]
        for i, (lbl, val, col) in enumerate(cells):
            grid.addWidget(_kv(lbl, val, col), i // 3, i % 3)
        as_lay.addLayout(grid)
        self.detail_layout.addWidget(as_box)

        # --- Milestones table ---
        m_box, m_lay = _section("Net-Worth Milestones")
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Year", "Age", "Net Worth", "Real (today)", "Portfolio"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hh = table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        for c in range(2, 5):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Stretch)

        # Pick milestone years: 0, 5, 10, retirement, 20, 30, horizon (dedup, in range)
        years_to_retire = max(0, a.retirement_age - a.current_age)
        candidates = sorted({0, 5, 10, years_to_retire, 20, 30, a.horizon_years})
        candidates = [y for y in candidates if 0 <= y < len(self._proj)]
        # Build stressed lookup if available
        stress_lookup = {p.year: p for p in (self._stress_proj or [])}
        if self._stress_proj:
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(["Year", "Age", "Net Worth", "Real (today)", "Portfolio", "Stressed NW"])
            hh.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        table.setRowCount(len(candidates))
        for r, y in enumerate(candidates):
            p = self._proj[y]
            table.setItem(r, 0, QTableWidgetItem(str(p.year)))
            table.setItem(r, 1, QTableWidgetItem(str(p.age)))
            table.setItem(r, 2, QTableWidgetItem(fmt_inr(p.net_worth_nominal, compact=True)))
            table.setItem(r, 3, QTableWidgetItem(fmt_inr(p.net_worth_real, compact=True)))
            table.setItem(r, 4, QTableWidgetItem(fmt_inr(p.portfolio_value, compact=True)))
            if self._stress_proj:
                sp = stress_lookup.get(y)
                table.setItem(r, 5, QTableWidgetItem(
                    fmt_inr(sp.net_worth_nominal, compact=True) if sp else "—"
                ))
        table.setMinimumHeight(max(120, 26 * (len(candidates) + 1)))
        m_lay.addWidget(table)
        self.detail_layout.addWidget(m_box)

        # --- Retirement readiness ---
        plan = self.svc.retirement_plan(self._baseline, a)
        r_box, r_lay = _section("Retirement Readiness")
        rgrid = QGridLayout(); rgrid.setSpacing(10)
        rcells = [
            ("Years to retirement",   str(plan.years_to_retirement), ""),
            ("Annual expenses today", fmt_inr(plan.annual_expenses_today, compact=True), ""),
            ("Corpus needed",         fmt_inr(plan.corpus_needed, compact=True), _C_BAD),
            ("Corpus projected",      fmt_inr(plan.corpus_projected, compact=True), _C_OK),
            ("Gap",                   fmt_inr(plan.gap, compact=True),
                                      _C_BAD if plan.gap > 0 else _C_OK),
            ("Additional SIP needed", fmt_inr(plan.required_additional_sip, compact=True),
                                      _C_WARN if plan.required_additional_sip > 0 else _C_OK),
        ]
        for i, (lbl, val, col) in enumerate(rcells):
            rgrid.addWidget(_kv(lbl, val, col), i // 3, i % 3)
        r_lay.addLayout(rgrid)

        if plan.on_track:
            status = QLabel("✓ On track for retirement on the current path.")
            status.setStyleSheet(f"color:{_C_OK}; font-weight:600; background:transparent;")
        else:
            status = QLabel(
                f"⚠ Short by {fmt_inr(plan.gap, compact=True)}. "
                f"Add {fmt_inr(plan.required_additional_sip, compact=True)} / month "
                f"for {plan.years_to_retirement} years to close the gap."
            )
            status.setStyleSheet(f"color:{_C_WARN}; font-weight:600; background:transparent;")
        status.setWordWrap(True)
        r_lay.addWidget(status)
        self.detail_layout.addWidget(r_box)

        self.detail_layout.addStretch(1)

    # Goal detail: forecast fields + linked holdings
    def _render_goal_detail(self, f) -> None:
        g = f.goal
        h_box, h_lay = _section(g.name or "Goal")
        grid = QGridLayout(); grid.setSpacing(10)
        cells = [
            ("Target",           fmt_inr(f.target, compact=True), ""),
            ("Funded",           fmt_inr(f.funded, compact=True), _C_OK),
            ("Gap",              fmt_inr(max(0.0, f.target - f.funded), compact=True),
                                 _C_BAD if f.target > f.funded else _C_OK),
            ("Target date",      fmt_date(f.target_date) if f.target_date else "—", ""),
            ("On-track date",    fmt_date(f.on_track_date) if f.on_track_date else "—",
                                 _C_OK if f.will_meet_target else _C_WARN),
            ("Months to target", str(f.months_to_target) if f.months_to_target else "—", ""),
            ("Required SIP",     fmt_inr(f.required_sip, compact=True), _C_WARN),
            ("Current SIP",      fmt_inr(f.estimated_current_sip, compact=True), _C_INFO),
            ("Expected return",  f"{(g.expected_return or 0.10) * 100:.1f}%", ""),
        ]
        for i, (lbl, val, col) in enumerate(cells):
            grid.addWidget(_kv(lbl, val, col), i // 3, i % 3)
        h_lay.addLayout(grid)

        if f.target_date and f.on_track_months is not None:
            if f.will_meet_target:
                msg = (f"✓ Will meet target by {fmt_date(f.on_track_date)} "
                       f"at the current SIP of "
                       f"{fmt_inr(f.estimated_current_sip, compact=True)} / mo.")
                colour = _C_OK
            else:
                msg = (f"⚠ Behind target. Increasing SIP to "
                       f"{fmt_inr(f.required_sip, compact=True)} / mo would meet "
                       f"{fmt_date(f.target_date)}.")
                colour = _C_BAD
        elif f.target_date and f.estimated_current_sip == 0:
            msg = ("No SIP funding detected. Link holdings to this goal "
                   "(Goals tab → Edit → Funded by Holdings) to project progress.")
            colour = _C_WARN
        else:
            msg = "Set a target date to see feasibility."
            colour = _C_MUTE
        status = QLabel(msg)
        status.setStyleSheet(f"color:{colour}; font-weight:600; background:transparent;")
        status.setWordWrap(True)
        h_lay.addWidget(status)
        self.detail_layout.addWidget(h_box)

        # Linked holdings
        ids = self.ctx.goal_linked_holding_ids(g.id)
        if ids:
            l_box, l_lay = _section("Funded by Holdings")
            holdings_by_id = self.ctx.holdings_by_id()
            for hid in ids:
                h = holdings_by_id.get(hid)
                if h is None:
                    continue
                row = QWidget()
                hl = QHBoxLayout(row); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(8)
                name = QLabel(h.name)
                name.setStyleSheet("color:#e7e0d4; font-size:12px; font-weight:600; background:transparent;")
                hl.addWidget(name, 1)
                meta_bits = []
                if h.sip_amount:
                    meta_bits.append(f"SIP {fmt_inr(h.sip_amount, compact=True)}/mo")
                meta_bits.append(f"Value {fmt_inr(h.current_value, compact=True)}")
                meta = QLabel("  ·  ".join(meta_bits))
                meta.setStyleSheet("color:#c4a878; font-size:12px; background:transparent;")
                hl.addWidget(meta, 0)
                l_lay.addWidget(row)
            self.detail_layout.addWidget(l_box)

        self.detail_layout.addStretch(1)
