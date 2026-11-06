from __future__ import annotations

from models.account import Account
from repositories.base_repo import BaseRepository


class AccountRepository(BaseRepository[Account]):
    table_name = "accounts"
    model_class = Account

    def list_active(self) -> list[Account]:
        return self.list_all("is_active = 1")

    def total_balance(self) -> float:
        row = self.db.fetch_one(
            "SELECT COALESCE(SUM(current_balance), 0) AS total "
            "FROM accounts WHERE is_active = 1 AND account_type != 'credit_card'"
        )
        return row["total"] if row else 0.0

    def update_balance(self, account_id: int, delta: float) -> None:
        self.db.execute(
            "UPDATE accounts SET current_balance = current_balance + ?, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (delta, account_id),
        )
        self.db.commit()
