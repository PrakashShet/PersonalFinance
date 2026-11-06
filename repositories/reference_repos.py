"""Small repositories: FX rates, the stock master, reminders."""
from __future__ import annotations

from typing import Optional

from db.connection import Database
from models.fx_rate import FxRate
from models.reminder import Reminder
from repositories.base_repo import BaseRepository


class FxRateRepository:
    """Keyed by currency code (no integer id), so not a BaseRepository."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def list_all(self) -> list[FxRate]:
        return [FxRate.from_row(r) for r in self.db.fetch_all(
            "SELECT * FROM fx_rates ORDER BY currency")]

    def get(self, currency: str) -> Optional[FxRate]:
        row = self.db.fetch_one("SELECT * FROM fx_rates WHERE currency = ?", (currency,))
        return FxRate.from_row(row) if row else None

    def upsert(self, currency: str, rate_to_inr: float, as_of: Optional[str]) -> None:
        self.db.execute(
            """
            INSERT INTO fx_rates (currency, rate_to_inr, as_of, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(currency) DO UPDATE SET
              rate_to_inr = excluded.rate_to_inr,
              as_of = excluded.as_of,
              updated_at = CURRENT_TIMESTAMP
            """,
            (currency, rate_to_inr, as_of),
        )
        self.db.commit()

    def delete(self, currency: str) -> None:
        self.db.execute("DELETE FROM fx_rates WHERE currency = ?", (currency,))
        self.db.commit()


class StockMasterRepository:
    """Read-only reference rows loaded from data/seed/stock_master.csv."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def lookup(self, symbol: str) -> Optional[dict]:
        if not symbol:
            return None
        row = self.db.fetch_one(
            "SELECT * FROM stock_master WHERE UPPER(symbol) = UPPER(?)", (symbol.strip(),)
        )
        return dict(row) if row else None

    def symbols(self) -> list[str]:
        return [r["symbol"] for r in self.db.fetch_all(
            "SELECT symbol FROM stock_master ORDER BY symbol")]


class ReminderRepository(BaseRepository[Reminder]):
    table_name = "reminders"
    model_class = Reminder

    def list_open(self) -> list[Reminder]:
        return self.list_all("COALESCE(is_done, 0) = 0 ORDER BY due_date")
