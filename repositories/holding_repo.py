from __future__ import annotations

from models.holding import Holding
from repositories.base_repo import BaseRepository


class HoldingRepository(BaseRepository[Holding]):
    table_name = "holdings"
    model_class = Holding

    def list_by_type(self, holding_type: str) -> list[Holding]:
        return self.list_all("holding_type = ? AND is_active = 1", (holding_type,))

    def list_active(self) -> list[Holding]:
        return self.list_all("is_active = 1")

    def total_invested(self) -> float:
        row = self.db.fetch_one(
            "SELECT COALESCE(SUM(invested_amount), 0) AS t FROM holdings WHERE is_active = 1"
        )
        return row["t"] if row else 0.0

    def total_current_value(self) -> float:
        row = self.db.fetch_one(
            "SELECT COALESCE(SUM(current_value), 0) AS t FROM holdings WHERE is_active = 1"
        )
        return row["t"] if row else 0.0
