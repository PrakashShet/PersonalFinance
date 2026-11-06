from __future__ import annotations

from typing import Optional

from models.budget import Budget
from repositories.base_repo import BaseRepository


class BudgetRepository(BaseRepository[Budget]):
    table_name = "budgets"
    model_class = Budget

    def list_with_categories(self) -> list:
        """Every budget joined with its category's name and kind."""
        return self.db.fetch_all(
            "SELECT b.*, c.name AS category_name, c.kind AS category_kind "
            "FROM budgets b JOIN categories c ON c.id = b.category_id "
            "ORDER BY CASE b.period WHEN 'monthly' THEN 0 ELSE 1 END, c.name COLLATE NOCASE"
        )

    def find(self, category_id: int, period: str) -> Optional[Budget]:
        row = self.db.fetch_one(
            "SELECT * FROM budgets WHERE category_id = ? AND period = ?",
            (category_id, period),
        )
        return Budget.from_row(row) if row else None

    def for_category(self, category_id: int) -> list[Budget]:
        return self.list_all("category_id = ?", (category_id,))
