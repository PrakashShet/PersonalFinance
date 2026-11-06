from __future__ import annotations

from typing import Optional

from models.liability import Liability
from repositories.base_repo import BaseRepository


class LiabilityRepository(BaseRepository[Liability]):
    table_name = "liabilities"
    model_class = Liability

    def list_active(self) -> list[Liability]:
        return self.list_all("is_active = 1")

    def find_by_account(self, account_id: int) -> Optional[Liability]:
        rows = self.list_all("account_id = ? ORDER BY is_active DESC, id", (account_id,))
        return rows[0] if rows else None

    def total_outstanding(self) -> float:
        row = self.db.fetch_one(
            "SELECT COALESCE(SUM(outstanding), 0) AS t FROM liabilities WHERE is_active = 1"
        )
        return row["t"] if row else 0.0
