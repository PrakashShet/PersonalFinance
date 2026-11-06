from __future__ import annotations

from models.liability import Liability
from repositories.base_repo import BaseRepository


class LiabilityRepository(BaseRepository[Liability]):
    table_name = "liabilities"
    model_class = Liability

    def list_active(self) -> list[Liability]:
        return self.list_all("is_active = 1")

    def total_outstanding(self) -> float:
        row = self.db.fetch_one(
            "SELECT COALESCE(SUM(outstanding), 0) AS t FROM liabilities WHERE is_active = 1"
        )
        return row["t"] if row else 0.0
