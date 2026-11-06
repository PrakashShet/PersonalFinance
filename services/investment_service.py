"""Business logic for investment holdings (SIP, FD, stocks, gold, insurance)."""
from __future__ import annotations

from collections import defaultdict
from typing import Callable

from config.constants import ASSET_BUCKETS, HoldingType
from models.holding import Holding
from repositories.holding_repo import HoldingRepository


class InvestmentService:
    def __init__(
        self,
        repo: HoldingRepository,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        self.repo = repo
        self._on_change = on_change

    def list_active(self) -> list[Holding]:
        return self.repo.list_active()

    def get(self, holding_id: int) -> Holding | None:
        return self.repo.get_by_id(holding_id)

    def add_holding(self, holding: Holding) -> int:
        self._normalize_amounts(holding)
        new_id = self.repo.insert(holding)
        if self._on_change is not None:
            self._on_change("holdings")
        return new_id

    def update_holding(self, holding: Holding) -> None:
        if holding.id is None:
            raise ValueError("Cannot update a holding without an id")
        self._normalize_amounts(holding)
        self.repo.update(holding)
        if self._on_change is not None:
            self._on_change("holdings")

    def delete_holding(self, holding_id: int) -> None:
        self.repo.delete(holding_id)
        if self._on_change is not None:
            self._on_change("holdings")

    def toggle_active(self, holding: Holding) -> None:
        holding.is_active = 0 if holding.is_active else 1
        self.repo.update(holding)
        if self._on_change is not None:
            self._on_change("holdings")

    @staticmethod
    def _normalize_amounts(holding: Holding) -> None:
        if holding.quantity and holding.avg_price and not holding.invested_amount:
            holding.invested_amount = holding.quantity * holding.avg_price
        if holding.quantity and holding.current_price and not holding.current_value:
            holding.current_value = holding.quantity * holding.current_price

    def total_portfolio_value(self) -> float:
        return self.repo.total_current_value()

    def total_invested(self) -> float:
        return self.repo.total_invested()

    def asset_allocation(self) -> dict[str, float]:
        """Returns {bucket: current_value} for the dashboard donut."""
        holdings = self.repo.list_active()
        buckets: dict[str, float] = defaultdict(float)
        for h in holdings:
            assigned = False
            for bucket, types in ASSET_BUCKETS.items():
                if h.holding_type in [t.value for t in types]:
                    buckets[bucket] += h.current_value
                    assigned = True
                    break
            if not assigned:
                buckets["other"] += h.current_value
        return dict(buckets)

    def stock_breakdown_by_cap(self) -> dict[str, float]:
        """SME / Small / Mid / Large cap exposure."""
        stocks = self.repo.list_by_type(HoldingType.STOCK.value)
        result: dict[str, float] = defaultdict(float)
        for s in stocks:
            cap = s.market_cap or "unclassified"
            result[cap] += s.current_value
        return dict(result)

    def upcoming_maturities(self, within_days: int = 30) -> list[Holding]:
        """FDs and term-insurance premiums coming due."""
        from datetime import datetime, timedelta
        cutoff = (datetime.now() + timedelta(days=within_days)).strftime("%Y-%m-%d")
        rows = self.repo.db.fetch_all(
            """
            SELECT * FROM holdings
            WHERE is_active = 1
              AND ((holding_type = 'fd' AND maturity_date <= ?)
                OR (holding_type = 'term_insurance' AND premium_due_date <= ?))
            ORDER BY COALESCE(maturity_date, premium_due_date)
            """,
            (cutoff, cutoff),
        )
        return [Holding.from_row(r) for r in rows]
