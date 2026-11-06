from __future__ import annotations

from models.income import IncomeSource
from repositories.base_repo import BaseRepository


class IncomeRepository(BaseRepository[IncomeSource]):
    table_name = "income_sources"
    model_class = IncomeSource

    def list_active(self) -> list[IncomeSource]:
        return self.list_all("is_active = 1")
