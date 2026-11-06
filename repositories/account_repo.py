from __future__ import annotations

from models.account import Account
from repositories.base_repo import BaseRepository


class AccountRepository(BaseRepository[Account]):
    table_name = "accounts"
    model_class = Account

    def list_active(self) -> list[Account]:
        return self.list_all("is_active = 1 ORDER BY id")

    def total_balance(self) -> float:
        """Plain SUM across currencies - prefer ``balances_by_currency`` plus an
        FX conversion (NetWorthService does this) when currencies can be mixed."""
        row = self.db.fetch_one(
            "SELECT COALESCE(SUM(current_balance), 0) AS total "
            "FROM accounts WHERE is_active = 1 AND account_type != 'credit_card'"
        )
        return row["total"] if row else 0.0

    def balances_by_currency(self) -> dict[str, float]:
        """Active, non-credit-card balances grouped by currency."""
        rows = self.db.fetch_all(
            "SELECT COALESCE(currency, 'INR') AS ccy, COALESCE(SUM(current_balance), 0) AS total "
            "FROM accounts WHERE is_active = 1 AND account_type != 'credit_card' "
            "GROUP BY COALESCE(currency, 'INR')"
        )
        return {r["ccy"]: float(r["total"]) for r in rows}

    def currencies_in_use(self) -> set[str]:
        rows = self.db.fetch_all(
            "SELECT DISTINCT COALESCE(currency, 'INR') AS ccy FROM accounts WHERE is_active = 1"
        )
        return {r["ccy"] for r in rows}

    def update_balance(self, account_id: int, delta: float) -> None:
        self.db.execute(
            "UPDATE accounts SET current_balance = ROUND(current_balance + ?, 2), "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (delta, account_id),
        )
        self.db.commit()
