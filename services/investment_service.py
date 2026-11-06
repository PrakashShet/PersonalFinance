"""Business logic for investment holdings (SIP, FD, stocks, gold, insurance).

Term insurance is stored as a holding but it is **protection, not an
investment**: it has no market value, and its premium is a cost. It is kept out
of every investment figure (invested, value, P&L, return, movers) and reported
on its own by :meth:`protection_summary`. Counting it used to show the policy as
a permanent -100% "worst mover" and drag the portfolio's return down.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Optional

from config.constants import ASSET_BUCKETS, HoldingType
from models.holding import Holding
from repositories.holding_repo import HoldingRepository
from utils.calculators import xirr

PROTECTION_TYPES = frozenset({HoldingType.TERM_INSURANCE.value})

# Annualising a return over a few weeks produces silly numbers.
MIN_DAYS_FOR_ANNUALISED = 90


@dataclass
class PortfolioSummary:
    invested: float
    value: float
    pnl: float
    return_pct: float
    count: int
    annualised: Optional[float]      # XIRR as a fraction (0.12 = 12%), or None


@dataclass
class ProtectionSummary:
    count: int
    sum_assured: float
    annual_premium: float


class InvestmentService:
    def __init__(
        self,
        repo: HoldingRepository,
        on_change: Callable[[str], None] | None = None,
        txn_repo=None,
        stock_master=None,
    ) -> None:
        self.repo = repo
        self._on_change = on_change
        self._txn_repo = txn_repo
        self._stock_master = stock_master

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change("holdings")

    # ------------------------------------------------------------- reads
    def list_active(self) -> list[Holding]:
        return self.repo.list_active()

    def list_all(self, include_inactive: bool = False) -> list[Holding]:
        if include_inactive:
            return self.repo.list_all("1 = 1 ORDER BY is_active DESC, id")
        return self.repo.list_active()

    def get(self, holding_id: int) -> Holding | None:
        return self.repo.get_by_id(holding_id)

    @staticmethod
    def is_protection(h: Holding) -> bool:
        return h.holding_type in PROTECTION_TYPES

    def investments(self, holdings: Optional[list[Holding]] = None) -> list[Holding]:
        """Active holdings that are investments (insurance excluded)."""
        hs = holdings if holdings is not None else self.repo.list_active()
        return [h for h in hs if not self.is_protection(h)]

    # ------------------------------------------------------------- writes
    def add_holding(self, holding: Holding) -> int:
        self._normalize_amounts(holding)
        new_id = self.repo.insert(holding)
        self._changed()
        return new_id

    def update_holding(self, holding: Holding) -> None:
        if holding.id is None:
            raise ValueError("Cannot update a holding without an id")
        self._normalize_amounts(holding)
        self.repo.update(holding)
        self._changed()

    def delete_holding(self, holding_id: int) -> None:
        self.repo.delete(holding_id)
        self._changed()

    def toggle_active(self, holding: Holding) -> None:
        holding.is_active = 0 if holding.is_active else 1
        self.repo.update(holding)
        self._changed()

    @staticmethod
    def _normalize_amounts(holding: Holding) -> None:
        if holding.quantity and holding.avg_price and not holding.invested_amount:
            holding.invested_amount = holding.quantity * holding.avg_price
        if holding.quantity and holding.current_price and not holding.current_value:
            holding.current_value = holding.quantity * holding.current_price

    # ------------------------------------------------------------ figures
    def total_portfolio_value(self) -> float:
        return sum(h.current_value for h in self.investments())

    def total_invested(self) -> float:
        return sum(h.invested_amount for h in self.investments())

    def portfolio_summary(self, holdings: Optional[list[Holding]] = None) -> PortfolioSummary:
        inv = self.investments(holdings)
        invested = sum(h.invested_amount for h in inv)
        value = sum(h.current_value for h in inv)
        pnl = value - invested
        return PortfolioSummary(
            invested=invested,
            value=value,
            pnl=pnl,
            return_pct=(pnl / invested * 100.0) if invested > 0 else 0.0,
            count=len(inv),
            annualised=self._xirr_for(inv),
        )

    def protection_summary(self) -> ProtectionSummary:
        policies = [h for h in self.repo.list_active() if self.is_protection(h)]
        return ProtectionSummary(
            count=len(policies),
            sum_assured=sum(h.sum_assured or 0.0 for h in policies),
            annual_premium=sum(h.premium_amount or 0.0 for h in policies),
        )

    def asset_allocation(self) -> dict[str, float]:
        """Returns {bucket: current_value} for investments (no insurance)."""
        buckets: dict[str, float] = defaultdict(float)
        for h in self.investments():
            for bucket, types in ASSET_BUCKETS.items():
                if h.holding_type in [t.value for t in types]:
                    buckets[bucket] += h.current_value
                    break
            else:
                buckets["other"] += h.current_value
        buckets.pop("insurance", None)
        return dict(buckets)

    def stock_breakdown_by_cap(self) -> dict[str, float]:
        """SME / Small / Mid / Large cap exposure."""
        stocks = self.repo.list_by_type(HoldingType.STOCK.value)
        result: dict[str, float] = defaultdict(float)
        for s in stocks:
            cap = s.market_cap or "unclassified"
            result[cap] += s.current_value
        return dict(result)

    def movers(self, n: int = 1) -> tuple[list[Holding], list[Holding]]:
        """(best, worst) investments by return; insurance never appears."""
        ranked = sorted(
            (h for h in self.investments() if h.invested_amount > 0),
            key=lambda h: h.return_pct, reverse=True,
        )
        best = ranked[:n]
        worst = [h for h in reversed(ranked) if h not in best][:n]
        return best, worst

    def upcoming_maturities(self, within_days: int = 30) -> list[Holding]:
        """FDs and term-insurance premiums coming due."""
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

    # ------------------------------------------------------ annualised (XIRR)
    def annualised_return(self, holding: Holding) -> Optional[float]:
        """XIRR of one holding as a fraction, or None when it isn't meaningful."""
        if self.is_protection(holding):
            return None
        return self._xirr_for([holding])

    def _flows(self, holding: Holding) -> list[tuple[date, float]]:
        """Dated cashflows: linked buy/sell transactions, plus any part of the
        recorded cost they don't explain, placed on the purchase date.

        Usually only recent instalments are logged as transactions while the
        invested amount covers years of history; using the transactions alone
        made a 4-year-old fund look like a +890% a year return."""
        flows: list[tuple[date, float]] = []
        net_logged = 0.0
        if self._txn_repo is not None and holding.id is not None:
            for r in self._txn_repo.holding_cashflows(holding.id):
                d = _as_date(r["txn_date"])
                if d is None:
                    continue
                amt = float(r["amount"] or 0.0)
                buy = r["txn_type"] == "investment_buy"
                flows.append((d, -amt if buy else amt))
                net_logged += amt if buy else -amt
        untracked = (holding.invested_amount or 0.0) - net_logged
        if untracked > 1.0:
            start = _as_date(holding.purchase_date)
            if start is None and flows:
                start = min(d for d, _ in flows)
            if start is None:
                return []          # cost with no date - an annual rate would be a guess
            flows.append((start, -untracked))
        return flows

    def _xirr_for(self, holdings: list[Holding]) -> Optional[float]:
        today = date.today()
        flows: list[tuple[date, float]] = []
        terminal = 0.0
        for h in holdings:
            f = self._flows(h)
            if not f:
                continue
            flows.extend(f)
            terminal += h.current_value
        if not flows or terminal <= 0:
            return None
        start = min(d for d, _ in flows)
        if (today - start).days < MIN_DAYS_FOR_ANNUALISED:
            return None
        cashflows = [((d - start).days, amt) for d, amt in flows]
        cashflows.append(((today - start).days, terminal))
        try:
            rate = xirr(cashflows)
        except ValueError:
            return None
        return rate if -0.99 < rate < 10 else None

    # ---------------------------------------------------------- stock master
    def lookup_stock(self, symbol: str) -> Optional[dict]:
        if self._stock_master is None or not symbol:
            return None
        return self._stock_master.lookup(symbol)


def _as_date(value) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
