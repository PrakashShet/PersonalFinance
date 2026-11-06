"""Goals CRUD and goal ↔ holding links."""
from __future__ import annotations

from typing import Callable

from models.goal import Goal
from repositories.goal_holding_repo import GoalHoldingRepository
from repositories.goal_repo import GoalRepository
from repositories.holding_repo import HoldingRepository
from services.projection_service import ProjectionService


class GoalService:
    def __init__(
        self,
        goal_repo: GoalRepository,
        goal_holding_repo: GoalHoldingRepository,
        holding_repo: HoldingRepository,
        projection_service: ProjectionService | None = None,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        self._goals = goal_repo
        self._links = goal_holding_repo
        self._holdings = holding_repo
        self._projection = projection_service or ProjectionService()
        self._on_change = on_change

    def list_all(self) -> list[Goal]:
        return self._goals.list_all()

    def list_active(self) -> list[Goal]:
        return self._goals.list_active()

    def get(self, goal_id: int) -> Goal | None:
        return self._goals.get_by_id(goal_id)

    def holdings_for_dialog(self) -> list[tuple[int, str, float]]:
        return [
            (h.id, h.name, h.current_value)
            for h in self._holdings.list_active()
        ]

    def linked_holding_ids(self, goal_id: int) -> list[int]:
        return self._links.holding_ids_for_goal(goal_id)

    def linked_holding_names(self, goal_id: int) -> list[str]:
        names = {h.id: h.name for h in self._holdings.list_active()}
        return [
            names.get(hid, f"#{hid}")
            for hid in self._links.holding_ids_for_goal(goal_id)
        ]

    def required_sip(self, goal: Goal) -> float:
        return self._projection.required_sip_for_goal(goal)

    def sync_funding_from_holdings(self, goal_id: int) -> None:
        if not self._links.holding_ids_for_goal(goal_id):
            return
        goal = self._goals.get_by_id(goal_id)
        if goal is None:
            return
        goal.current_amount = self._links.funded_amount(goal_id)
        self._goals.update(goal)
        if self._on_change is not None:
            self._on_change("goals")

    def refresh_all_linked_amounts(self, goals: list[Goal]) -> None:
        for goal in goals:
            if goal.id is not None and self._links.holding_ids_for_goal(goal.id):
                funded = self._links.funded_amount(goal.id)
                if abs((goal.current_amount or 0.0) - funded) > 0.005:
                    goal.current_amount = funded
                    self._goals.update(goal)

    def create(self, goal: Goal, holding_ids: list[int] | None = None) -> int:
        if not goal.name.strip():
            raise ValueError("Goal name is required")
        goal_id = self._goals.insert(goal)
        if holding_ids:
            self._links.set_for_goal(goal_id, holding_ids)
            self.sync_funding_from_holdings(goal_id)
            if self._on_change is not None:
                self._on_change("goal_holdings")
        if self._on_change is not None:
            self._on_change("goals")
        return goal_id

    def update(self, goal: Goal, holding_ids: list[int] | None = None) -> None:
        if goal.id is None:
            raise ValueError("Cannot update a goal without an id")
        if not goal.name.strip():
            raise ValueError("Goal name is required")
        self._goals.update(goal)
        if holding_ids is not None:
            self._links.set_for_goal(goal.id, holding_ids)
            self.sync_funding_from_holdings(goal.id)
            if self._on_change is not None:
                self._on_change("goal_holdings")
        if self._on_change is not None:
            self._on_change("goals")

    def set_status(self, goal: Goal, status: str) -> None:
        goal.status = status
        self._goals.update(goal)
        if self._on_change is not None:
            self._on_change("goals")

    def toggle_paused(self, goal: Goal) -> None:
        goal.status = "active" if goal.status == "paused" else "paused"
        self._goals.update(goal)
        if self._on_change is not None:
            self._on_change("goals")

    def delete(self, goal_id: int) -> None:
        self._goals.delete(goal_id)
        if self._on_change is not None:
            self._on_change("goals")
            self._on_change("goal_holdings")
