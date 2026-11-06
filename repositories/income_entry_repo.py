from __future__ import annotations

from typing import Optional

from models.income_entry import IncomeEntry
from repositories.base_repo import BaseRepository


class IncomeEntryRepository(BaseRepository[IncomeEntry]):
    table_name = "income_entries"
    model_class = IncomeEntry

    def list_for_source(self, source_id: int) -> list[IncomeEntry]:
        return self.list_all(
            "income_source_id = ? ORDER BY period_month DESC", (source_id,)
        )

    def get_for_period(self, source_id: int, period_month: str) -> Optional[IncomeEntry]:
        row = self.db.fetch_one(
            "SELECT * FROM income_entries "
            "WHERE income_source_id = ? AND period_month = ?",
            (source_id, period_month),
        )
        return IncomeEntry.from_row(row) if row else None

    def total_received(self, period_month: str) -> float:
        row = self.db.fetch_one(
            "SELECT COALESCE(SUM(actual_amount), 0) AS t "
            "FROM income_entries WHERE period_month = ?",
            (period_month,),
        )
        return row["t"] if row else 0.0
