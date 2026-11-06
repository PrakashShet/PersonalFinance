from __future__ import annotations

from models.goal import Goal
from repositories.base_repo import BaseRepository


class GoalRepository(BaseRepository[Goal]):
    table_name = "goals"
    model_class = Goal

    def list_active(self) -> list[Goal]:
        return self.list_all("status = 'active'")
