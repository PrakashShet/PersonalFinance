"""Goals tab - goal cards/list with progress, SIP requirements, CRUD."""
from __future__ import annotations

from datetime import date
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from models.goal import Goal
from services.app_context import AppContext
from ui.theme.badges import (
    FALLBACK_BADGE,
    GOAL_PRIORITY_BADGE,
    GOAL_STATUS_BADGE,
)
from ui.dialogs.goal_dialog import GoalDialog
from ui.widgets.goal_tile import GoalTile
from ui.widgets.kpi_card import KpiCard
from utils.formatters import fmt_inr, fmt_pct, fmt_date


PRIORITY_LABELS = {1: "P1", 2: "P2", 3: "P3", 4: "P4", 5: "P5"}

STATUS_FILTER_ORDER = ["all", "active", "achieved", "paused", "abandoned"]
STATUS_FILTER_LABELS = {
    "all": "All", "active": "Active", "achieved": "Achieved",
    "paused": "Paused", "abandoned": "Abandoned",
}


def _months_remaining(target_date: Optional[str]) -> int:
    if not target_date:
        return 0
    try:
        td = date.fromisoformat(target_date)
        today = date.today()
        return max(0, (td.year - today.year) * 12 + (td.month - today.month))
    except ValueError:
        return 0


def _time_left_label(months: int) -> str:
    if months <= 0:
        return "Overdue"
    y, m = divmod(months, 12)
    parts = []
    if y:
        parts.append(f"{y}y")
    if m:
        parts.append(f"{m}m")
    return " ".join(parts) or "< 1m"


class GoalsView(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._topics = {"goals", "goal_holdings", "holdings"}
        self._dirty = True
        self._svc = ctx.goal_service
        self._goals: list[Goal] = []
        self._tiles: list[GoalTile] = []
        self._active_filter = "active"
        self._selected_id: Optional[int] = None
        self.ctx.events.changed.connect(self._on_data_changed)
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        hdr = QHBoxLayout()
        title = QLabel("Goals")
        title.setObjectName("pageTitle")
        hdr.addWidget(title)
        hdr.addStretch()
        self.add_btn = QPushButton("Add Goal")
        self.add_btn.setObjectName("primaryBtn")
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self._on_add)
        hdr.addWidget(self.add_btn)
        root.addLayout(hdr)

        kpi_row = QGridLayout()
        kpi_row.setSpacing(12)
        self.kpi_total   = KpiCard("Total Target",   "")
        self.kpi_current = KpiCard("Total Saved",    "")
        self.kpi_sip     = KpiCard("Total Req. SIP", "")
        self.kpi_count   = KpiCard("Active Goals",   "")
        for i, w in enumerate([self.kpi_total, self.kpi_current,
                                self.kpi_sip, self.kpi_count]):
            kpi_row.addWidget(w, 0, i)
        root.addLayout(kpi_row)

        pill_row = QHBoxLayout()
        pill_row.setSpacing(6)
        self._pills: dict[str, QPushButton] = {}
        for key in STATUS_FILTER_ORDER:
            btn = QPushButton(STATUS_FILTER_LABELS[key])
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("filterPill", True)
            btn.clicked.connect(lambda _c, k=key: self._on_filter(k))
            pill_row.addWidget(btn)
            self._pills[key] = btn
        self._pills["active"].setChecked(True)
        pill_row.addStretch()
        root.addLayout(pill_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Scrollable list of goal tiles
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tile_container = QWidget()
        self.tile_layout = QVBoxLayout(self.tile_container)
        self.tile_layout.setContentsMargins(0, 4, 6, 4)
        self.tile_layout.setSpacing(10)
        self.tile_layout.addStretch(1)
        self.scroll.setWidget(self.tile_container)
        self.scroll.setMinimumHeight(180)

        self.empty_label = QLabel("No goals here. Click \"Add Goal\" to create one.")
        self.empty_label.setObjectName("tileFlags")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.hide()

        action_bar = QHBoxLayout()
        self.edit_btn   = QPushButton("Edit")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self._on_edit)
        self.toggle_btn = QPushButton("Pause")
        self.toggle_btn.setEnabled(False)
        self.toggle_btn.clicked.connect(self._on_toggle)
        self.delete_btn = QPushButton("Delete")
        self.delete_btn.setEnabled(False)
        self.delete_btn.setObjectName("dangerBtn")
        self.delete_btn.clicked.connect(self._on_delete)
        action_bar.addWidget(self.edit_btn)
        action_bar.addWidget(self.toggle_btn)
        action_bar.addWidget(self.delete_btn)
        action_bar.addStretch()

        list_pane = QWidget()
        tp = QVBoxLayout(list_pane)
        tp.setContentsMargins(0, 0, 0, 0)
        tp.setSpacing(6)
        tp.addWidget(self.scroll, 1)
        tp.addWidget(self.empty_label)
        tp.addLayout(action_bar)
        splitter.addWidget(list_pane)

        # Right: placeholder until a goal is selected, then the detail panel
        self.detail_stack = QStackedWidget()
        placeholder = QLabel("Select a goal to see its details.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setObjectName("tileFlags")
        placeholder.setWordWrap(True)
        self.detail_stack.addWidget(placeholder)
        self.detail = _GoalDetailPanel()
        self.detail_stack.addWidget(self.detail)
        splitter.addWidget(self.detail_stack)

        splitter.setSizes([520, 520])
        root.addWidget(splitter, 1)

    def _on_data_changed(self, topic: str) -> None:
        if topic in self._topics:
            self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty:
            self.refresh()

    def refresh(self) -> None:
        self._goals = self._svc.list_all()
        self._svc.refresh_all_linked_amounts(self._goals)
        self._goals = self._svc.list_all()
        self._refresh_tiles()
        self._refresh_kpis()
        self._dirty = False

    def _holdings_list(self) -> list:
        return self._svc.holdings_for_dialog()

    def _visible_goals(self) -> list[Goal]:
        if self._active_filter == "all":
            return self._goals
        return [g for g in self._goals if g.status == self._active_filter]

    def _refresh_tiles(self) -> None:
        for t in self._tiles:
            self.tile_layout.removeWidget(t)
            t.deleteLater()
        self._tiles = []
        while self.tile_layout.count():
            self.tile_layout.takeAt(0)

        visible = self._visible_goals()
        for g in visible:
            p = g.priority or 3
            pbg, pfg = GOAL_PRIORITY_BADGE.get(p, FALLBACK_BADGE)
            sbg, sfg = GOAL_STATUS_BADGE.get(g.status, FALLBACK_BADGE)
            pct = g.progress_pct
            bar_colour = "#16a34a" if pct >= 100 else "#f59e0b" if pct >= 50 else "#3b82f6"
            tile = GoalTile(
                g,
                status_label=g.status.title(),
                status_bg=sbg,
                status_fg=sfg,
                priority_label=PRIORITY_LABELS.get(p, f"P{p}"),
                priority_bg=pbg,
                priority_fg=pfg,
                saved_text=fmt_inr(g.current_amount, compact=True),
                target_text=fmt_inr(g.target_amount, compact=True),
                pct=int(pct),
                bar_colour=bar_colour,
                selected=(g.id == self._selected_id),
                on_click=self._on_tile_clicked,
                on_activate=self._on_tile_activated,
                parent=self.tile_container,
            )
            self._tiles.append(tile)
            self.tile_layout.addWidget(tile)
        self.tile_layout.addStretch(1)

        self.empty_label.setVisible(not visible)
        self.scroll.setVisible(bool(visible))
        self._update_buttons()

        sel = self._selected_goal()
        if sel is not None and any(t.goal.id == sel.id for t in self._tiles):
            self.detail.load(
                sel,
                self._svc.required_sip(sel),
                self._svc.linked_holding_names(sel.id),
            )
            self.detail_stack.setCurrentIndex(1)
        else:
            self.detail_stack.setCurrentIndex(0)

    def _refresh_kpis(self) -> None:
        active = [g for g in self._goals if g.status == "active"]
        total_target  = sum(g.target_amount  for g in active)
        total_current = sum(g.current_amount for g in active)
        total_sip = sum(self._svc.required_sip(g) for g in active)
        self.kpi_total.set_value(fmt_inr(total_target, compact=True))
        self.kpi_current.set_value(fmt_inr(total_current, compact=True))
        self.kpi_sip.set_value(fmt_inr(total_sip, compact=True))
        self.kpi_count.set_value(str(len(active)))

    def _on_filter(self, key: str) -> None:
        self._active_filter = key
        for k, btn in self._pills.items():
            btn.setChecked(k == key)
        self._selected_id = None
        self.detail_stack.setCurrentIndex(0)
        self._refresh_tiles()

    def _update_buttons(self) -> None:
        g = self._selected_goal()
        has_sel = g is not None
        self.edit_btn.setEnabled(has_sel)
        self.delete_btn.setEnabled(has_sel)
        self.toggle_btn.setEnabled(has_sel)
        if g is not None:
            self.toggle_btn.setText("Resume" if g.status == "paused" else "Pause")

    def _on_tile_clicked(self, g: Goal) -> None:
        self._selected_id = g.id
        for t in self._tiles:
            t.set_selected(t.goal.id == g.id)
        self._update_buttons()
        self.detail.load(
            g,
            self._svc.required_sip(g),
            self._svc.linked_holding_names(g.id),
        )
        self.detail_stack.setCurrentIndex(1)

    def _on_tile_activated(self, g: Goal) -> None:
        self._on_tile_clicked(g)
        self._on_edit()

    def _selected_goal(self) -> Optional[Goal]:
        if self._selected_id is None:
            return None
        return next((g for g in self._goals if g.id == self._selected_id), None)

    def _on_add(self) -> None:
        dlg = GoalDialog(self, holdings=self._holdings_list())
        if dlg.exec() == GoalDialog.DialogCode.Accepted:
            self._svc.create(dlg.get_goal(), dlg.selected_holding_ids())
            self.refresh()

    def _on_edit(self) -> None:
        g = self._selected_goal()
        if g is None:
            return
        dlg = GoalDialog(
            self,
            g,
            holdings=self._holdings_list(),
            linked_ids=self._svc.linked_holding_ids(g.id),
        )
        if dlg.exec() == GoalDialog.DialogCode.Accepted:
            self._svc.update(dlg.get_goal(), dlg.selected_holding_ids())
            self.refresh()

    def _on_toggle(self) -> None:
        g = self._selected_goal()
        if g is None:
            return
        self._svc.toggle_paused(g)
        self.refresh()

    def _on_delete(self) -> None:
        g = self._selected_goal()
        if g is None:
            return
        ans = QMessageBox.question(
            self, "Delete Goal",
            f"Delete '{g.name}'?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if ans == QMessageBox.StandardButton.Yes:
            self._svc.delete(g.id)
            self._selected_id = None
            self.refresh()


class _GoalDetailPanel(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setObjectName("breakdownPanel")
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        self._header = QLabel("")
        self._header.setObjectName("sectionLabel")
        f = self._header.font()
        f.setBold(True)
        f.setPointSize(f.pointSize() + 1)
        self._header.setFont(f)
        root.addWidget(self._header)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setTextVisible(True)
        self._progress.setFormat("%p%  saved")
        self._progress.setFixedHeight(22)
        root.addWidget(self._progress)

        self._grid_widget = QWidget()
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setHorizontalSpacing(32)
        self._grid.setVerticalSpacing(4)
        root.addWidget(self._grid_widget)
        root.addStretch()

    def load(self, g: Goal, req_sip: float, linked_names: Optional[list] = None) -> None:
        p = g.priority or 3
        self._header.setText(f"{g.name}  -  {g.status.title()}  (Priority {p})")

        pct = int(g.progress_pct)
        self._progress.setValue(min(100, pct))
        colour = "#16a34a" if pct >= 100 else "#f59e0b" if pct >= 50 else "#3b82f6"
        self._progress.setStyleSheet(
            f"QProgressBar::chunk {{ background-color: {colour}; border-radius: 4px; }}")

        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        gap = max(0, g.target_amount - g.current_amount)
        months = _months_remaining(g.target_date)

        fields = []

        def _add(label, value, colour=""):
            fields.append((label, value, colour))

        _add("Target Amount",   fmt_inr(g.target_amount))
        _add("Saved So Far",    fmt_inr(g.current_amount), "#16a34a")
        _add("Remaining Gap",   fmt_inr(gap),              "#dc2626")
        _add("Progress",        f"{g.progress_pct:.1f}%")
        if g.target_date:
            _add("Target Date",     fmt_date(g.target_date))
            _add("Time Left",       _time_left_label(months),
                 "#dc2626" if months == 0 else "")
        if req_sip > 0:
            _add("Required SIP/mo", fmt_inr(req_sip), "#1d4ed8")
        _add("Expected Return", fmt_pct(g.expected_return * 100))
        _add("Inflation Rate",  fmt_pct(g.inflation_rate  * 100))
        if linked_names:
            _add("Funded By", ", ".join(linked_names), "#16a34a")
        if g.notes:
            _add("Notes", g.notes)

        COLS = 3
        for i, (label, value, colour) in enumerate(fields):
            row, col = divmod(i, COLS)
            lbl = QLabel(label)
            lbl.setObjectName("kpiTitle")
            val = QLabel(value)
            val.setObjectName("kpiValue")
            vf = val.font()
            vf.setBold(True)
            val.setFont(vf)
            if colour:
                val.setStyleSheet(f"color: {colour};")
            self._grid.addWidget(lbl, row * 2,     col)
            self._grid.addWidget(val, row * 2 + 1, col)
