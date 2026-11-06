"""Goals - what you're saving for, how far along you are, what it takes."""
from __future__ import annotations

from datetime import date
from typing import Optional

from PyQt6.QtWidgets import QMessageBox

from models.goal import Goal
from ui.dialogs.goal_dialog import GoalDialog
from ui.theme.badges import GOAL_STATUS_TONE
from ui.views.master_detail import MasterDetailView
from ui.widgets.common import SegmentedControl, progress
from ui.widgets.detail_panel import DetailPanel
from ui.widgets.kpi_card import KpiCard
from ui.widgets.list_tile import ListTile
from ui.widgets.toast import notify
from utils.formatters import fmt_date, fmt_inr, fmt_pct

FILTERS = [("active", "Active"), ("achieved", "Achieved"), ("paused", "Paused"), ("all", "All")]
PRIORITY = {1: "Top priority", 2: "High priority", 3: "Medium priority", 4: "Low priority",
            5: "Someday"}


def _months_left(target_date: Optional[str]) -> Optional[int]:
    if not target_date:
        return None
    try:
        td = date.fromisoformat(target_date[:10])
    except ValueError:
        return None
    today = date.today()
    return (td.year - today.year) * 12 + (td.month - today.month)


def _time_left(months: Optional[int]) -> str:
    if months is None:
        return "No target date"
    if months <= 0:
        return "Target date passed"
    y, m = divmod(months, 12)
    return " ".join(p for p in (f"{y} yr" if y else "", f"{m} mo" if m else "") if p) + " left"


class GoalsView(MasterDetailView):
    title = "Goals"
    subtitle = "Save towards what matters. Link investments and progress updates itself."
    add_label = "Add goal"
    topics = frozenset({"goals", "goal_holdings", "holdings"})
    inactive_label = None
    empty_icon = "goals"
    empty_title = "No goals here"
    empty_text = "Set a goal - a house, education, retirement - and see the monthly amount it needs."
    select_hint = "Select a goal to see progress and the monthly amount needed."

    def __init__(self, ctx) -> None:
        self._filter = "active"
        super().__init__(ctx)

    def build_kpis(self):
        self.k_target = KpiCard("Total target", icon_name="goals")
        self.k_saved = KpiCard("Saved so far", icon_name="coins")
        self.k_sip = KpiCard("Needed per month", icon_name="repeat")
        self.k_count = KpiCard("Active goals", icon_name="check_circle")
        return [self.k_target, self.k_saved, self.k_sip, self.k_count]

    def build_filters(self):
        self.filter_seg = SegmentedControl(FILTERS, "active")
        self.filter_seg.changed.connect(self._on_filter)
        return self.filter_seg

    def fetch(self, include_inactive: bool):
        svc = self.ctx.goal_service
        goals = svc.list_all()
        svc.refresh_all_linked_amounts(goals)
        return svc.list_all()

    def filter_items(self, items):
        if self._filter == "all":
            return items
        return [g for g in items if g.status == self._filter]

    def refresh_kpis(self, items) -> None:
        svc = self.ctx.goal_service
        active = [g for g in items if g.status == "active"]
        target = sum(g.target_amount for g in active)
        saved = sum(g.current_amount for g in active)
        self.k_target.set_value(fmt_inr(target, compact=True))
        self.k_saved.set_value(fmt_inr(saved, compact=True))
        self.k_saved.set_hint(f"{saved / target * 100:.0f}% of target" if target else "")
        self.k_sip.set_value(fmt_inr(sum(svc.required_sip(g) for g in active), compact=True))
        self.k_sip.set_hint("to hit every target on time")
        self.k_count.set_value(str(len(active)))

    def make_tile(self, g: Goal, selected: bool) -> ListTile:
        pct = g.progress_pct
        months = _months_left(g.target_date)
        meta = " · ".join(x for x in [
            f"By {fmt_date(g.target_date, '%b %Y')}" if g.target_date else "",
            PRIORITY.get(g.priority or 3, "")] if x)
        badge = None if g.status == "active" else (g.status.title(), GOAL_STATUS_TONE.get(g.status, "neutral"))
        tone = "positive" if pct >= 100 else ("warning" if months is not None and months <= 0 else "")
        return ListTile(
            g.id, g.name, meta,
            value=f"{fmt_inr(g.current_amount, compact=True)} of {fmt_inr(g.target_amount, compact=True)}",
            badge=badge, progress_pct=pct, progress_tone=tone, icon_name="goals",
            muted=g.status in ("paused", "abandoned"), selected=selected,
        )

    def on_add(self) -> None:
        dlg = GoalDialog(self, holdings=self.ctx.goal_service.holdings_for_dialog())
        if dlg.exec() == GoalDialog.DialogCode.Accepted:
            goal = dlg.get_goal()
            self._selected_id = self.ctx.goal_service.create(goal, dlg.selected_holding_ids())
            self.refresh()
            notify(f"Added goal {goal.name}")

    def on_activate(self, g: Goal) -> None:
        self._edit()

    def _on_filter(self, key: str) -> None:
        self._filter = key
        self._selected_id = None
        self.refresh()

    def render_detail(self, g: Goal, panel: DetailPanel) -> None:
        svc = self.ctx.goal_service
        badges = [(g.status.title(), GOAL_STATUS_TONE.get(g.status, "neutral"))]
        panel.set_header(g.name, PRIORITY.get(g.priority or 3, ""), badges)
        panel.set_actions([
            ("Edit", self._edit, "primary", "edit"),
            ("Resume" if g.status == "paused" else "Pause", self._toggle, "secondary"),
            ("Delete", self._delete, "danger", "trash"),
        ])

        pct = g.progress_pct
        bar = progress(pct, "positive" if pct >= 100 else "", large=True)
        panel.add_section(f"{pct:.0f}% saved", bar)

        months = _months_left(g.target_date)
        gap = max(0.0, g.target_amount - g.current_amount)
        req = svc.required_sip(g)
        rows = [("Target", fmt_inr(g.target_amount)),
                ("Saved", fmt_inr(g.current_amount), "positive"),
                ("Still needed", fmt_inr(gap), "negative" if gap > 0 else "positive")]
        if g.target_date:
            rows.append(("Target date", fmt_date(g.target_date)))
            rows.append(("Time", _time_left(months), "warning" if (months or 0) <= 0 else None))
        if req > 0:
            rows.append(("Invest each month", fmt_inr(req), "accent"))
        panel.add_stats("Progress", rows)

        linked = svc.linked_holding_names(g.id)
        assumptions = [("Expected return", fmt_pct((g.expected_return or 0) * 100) + " a year"),
                       ("Inflation", fmt_pct((g.inflation_rate or 0) * 100) + " a year")]
        if linked:
            assumptions.append(("Funded by", ", ".join(linked)))
        panel.add_stats("Plan", assumptions, columns=2)
        if not linked and g.status == "active":
            panel.add_banner("Link the investments that fund this goal (Edit) and its "
                             "progress will update as they grow.", "info")
        if g.notes:
            panel.add_text(g.notes)

    # ----------------------------------------------------------- actions
    def _edit(self) -> None:
        g = self.selected()
        if g is None:
            return
        svc = self.ctx.goal_service
        dlg = GoalDialog(self, g, holdings=svc.holdings_for_dialog(),
                         linked_ids=svc.linked_holding_ids(g.id))
        if dlg.exec() == GoalDialog.DialogCode.Accepted:
            svc.update(dlg.get_goal(), dlg.selected_holding_ids())
            self.refresh()
            notify("Saved")

    def _toggle(self) -> None:
        g = self.selected()
        if g is not None:
            self.ctx.goal_service.toggle_paused(g)
            self.refresh()

    def _delete(self) -> None:
        g = self.selected()
        if g is None:
            return
        ans = QMessageBox.question(self, "Delete goal", f"Delete “{g.name}”? This can't be undone.",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
        if ans == QMessageBox.StandardButton.Yes:
            self.ctx.goal_service.delete(g.id)
            self._selected_id = None
            self.refresh()
            notify("Deleted")
