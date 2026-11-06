"""Tests for NetWorthService: balance sheet computation and snapshots."""
from __future__ import annotations

from db.connection import Database
from models.account import Account
from models.holding import Holding
from models.liability import Liability
from repositories.account_repo import AccountRepository
from repositories.holding_repo import HoldingRepository
from repositories.liability_repo import LiabilityRepository
from services.net_worth_service import NetWorthService


def _service(db: Database) -> NetWorthService:
    return NetWorthService(db, AccountRepository(db), HoldingRepository(db), LiabilityRepository(db))


def test_compute_balance_sheet(temp_db: Database):
    AccountRepository(temp_db).insert(
        Account(name="Savings", account_type="savings", current_balance=100_000.0)
    )
    HoldingRepository(temp_db).insert(
        Holding(name="SIP A", holding_type="sip", invested_amount=40_000.0, current_value=50_000.0)
    )
    LiabilityRepository(temp_db).insert(
        Liability(name="Car Loan", liability_type="car_loan", outstanding=30_000.0)
    )

    svc = _service(temp_db)
    bs = svc.compute()

    assert bs.cash_and_bank == 100_000.0
    assert bs.investments == 50_000.0
    assert bs.total_assets == 150_000.0
    assert bs.total_liabilities == 30_000.0
    assert bs.net_worth == 120_000.0
    assert bs.breakdown["cash_and_bank"] == 100_000.0


def test_take_snapshot_inserts_row(temp_db: Database):
    AccountRepository(temp_db).insert(
        Account(name="Savings", account_type="savings", current_balance=10_000.0)
    )
    svc = _service(temp_db)
    svc.take_snapshot()

    rows = temp_db.fetch_all("SELECT * FROM net_worth_snapshots")
    assert len(rows) == 1
    assert rows[0]["net_worth"] == 10_000.0

    # Re-running on the same day replaces the row (INSERT OR REPLACE on date).
    svc.take_snapshot()
    rows = temp_db.fetch_all("SELECT * FROM net_worth_snapshots")
    assert len(rows) == 1
