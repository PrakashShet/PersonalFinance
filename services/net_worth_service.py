"""Net worth and balance-sheet calculation."""
from __future__ import annotations

import json
from datetime import date
from dataclasses import dataclass

from db.connection import Database
from repositories.account_repo import AccountRepository
from repositories.holding_repo import HoldingRepository
from repositories.liability_repo import LiabilityRepository


@dataclass
class BalanceSheet:
    cash_and_bank: float
    investments: float
    total_assets: float
    total_liabilities: float
    net_worth: float
    breakdown: dict


class NetWorthService:
    def __init__(
        self,
        db: Database,
        accounts: AccountRepository,
        holdings: HoldingRepository,
        liabilities: LiabilityRepository,
    ) -> None:
        self.db = db
        self.accounts = accounts
        self.holdings = holdings
        self.liabilities = liabilities

    def compute(self) -> BalanceSheet:
        cash = self.accounts.total_balance()
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
        )

    def take_snapshot(self) -> None:
        bs = self.compute()
        today = date.today().isoformat()
        self.db.execute(
            """
            INSERT OR REPLACE INTO net_worth_snapshots
              (snapshot_date, total_assets, total_liabilities, net_worth, breakdown_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (today, bs.total_assets, bs.total_liabilities, bs.net_worth, json.dumps(bs.breakdown)),
        )
        self.db.commit()
