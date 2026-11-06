"""Net worth, the balance sheet, and the daily snapshot history."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from db.connection import Database
from models.snapshot import NetWorthSnapshot
from repositories.account_repo import AccountRepository
from repositories.holding_repo import HoldingRepository
from repositories.liability_repo import LiabilityRepository
from repositories.snapshot_repo import SnapshotRepository


@dataclass
class BalanceSheet:
    cash_and_bank: float
    investments: float
    total_assets: float
    total_liabilities: float
    net_worth: float
    breakdown: dict
    # Balances in currencies with no FX rate: {currency: amount}. They are NOT
    # included in the totals above - the UI asks for a rate instead.
    unconverted: dict = field(default_factory=dict)


@dataclass
class NetWorthChange:
    amount: float
    since: str            # ISO date of the snapshot compared against


class NetWorthService:
    def __init__(
        self,
        db: Database,
        accounts: AccountRepository,
        holdings: HoldingRepository,
        liabilities: LiabilityRepository,
        fx_service=None,
        snapshots: Optional[SnapshotRepository] = None,
    ) -> None:
        self.db = db
        self.accounts = accounts
        self.holdings = holdings
        self.liabilities = liabilities
        self._fx = fx_service
        self.snapshots = snapshots or SnapshotRepository(db)

    def _cash(self) -> tuple[float, dict]:
        total = 0.0
        unconverted: dict[str, float] = {}
        for ccy, amount in self.accounts.balances_by_currency().items():
            if self._fx is not None:
                value = self._fx.convert(amount, ccy)
            else:
                value = amount if ccy == "INR" else None
            if value is None:
                unconverted[ccy] = amount
            else:
                total += value
        return total, unconverted

    def compute(self) -> BalanceSheet:
        cash, unconverted = self._cash()
        investments = self.holdings.total_current_value()
        total_assets = cash + investments
        total_liab = self.liabilities.total_outstanding()
        net_worth = total_assets - total_liab

        return BalanceSheet(
            cash_and_bank=cash,
            investments=investments,
            total_assets=total_assets,
            total_liabilities=total_liab,
            net_worth=net_worth,
            breakdown={
                "cash_and_bank": cash,
                "investments": investments,
                "liabilities": total_liab,
            },
            unconverted=unconverted,
        )

    def take_snapshot(self) -> None:
        """Record today's figures (one row per day; later calls replace it)."""
        bs = self.compute()
        self.snapshots.upsert(
            date.today().isoformat(),
            bs.total_assets,
            bs.total_liabilities,
            bs.net_worth,
            json.dumps(bs.breakdown),
        )

    def history(self) -> list[NetWorthSnapshot]:
        return self.snapshots.list_ordered()

    def change_since(self, days: int = 30) -> Optional[NetWorthChange]:
        """Net worth now vs the newest snapshot at least ``days`` old."""
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        past = self.snapshots.on_or_before(cutoff)
        if past is None:
            history = self.history()
            past = history[0] if history and history[0].snapshot_date < date.today().isoformat() else None
        if past is None:
            return None
        return NetWorthChange(self.compute().net_worth - past.net_worth, past.snapshot_date)
