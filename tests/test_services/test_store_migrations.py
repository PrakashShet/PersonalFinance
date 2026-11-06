"""Store format migrations (JSON level)."""
from __future__ import annotations

from datetime import date

import pytest

from services import ledger
from services.store_migrations import (
    STORE_VERSION,
    StoreVersionError,
    migrate,
)

TODAY = date(2026, 11, 6)


def _tables(accounts, txns):
    return {"accounts.json": accounts, "transactions.json": txns}


def test_v2_converts_opening_income_to_adjustment():
    accounts = [{"id": 1, "name": "Bank", "is_active": 1,
                 "opening_balance": 1000.0, "current_balance": 1000.0}]
    txns = [{"id": 1, "txn_date": "2026-01-01", "txn_type": "income", "amount": 1000.0,
             "account_id": 1, "category_id": 8, "tags": "opening-balance"}]
    tables = _tables(accounts, txns)
    migrate(tables, from_version=1, today=TODAY)

    assert txns[0]["txn_type"] == "adjustment"
    assert txns[0]["category_id"] is None
    assert len(txns) == 1                     # already explained - nothing added


def test_v2_adds_opening_entry_and_reconciliation_so_ledger_explains_balance():
    accounts = [
        {"id": 1, "name": "Salary", "is_active": 1, "opening_balance": 50_000.0,
         "current_balance": 130_000.0, "created_at": "2026-05-24 10:00:00"},
        {"id": 2, "name": "Wallet", "is_active": 1, "opening_balance": 0.0,
         "current_balance": 2_500.0},
        {"id": 3, "name": "Old", "is_active": 0, "opening_balance": 0.0,
         "current_balance": 9_999.0},
    ]
    txns = [
        {"id": 1, "txn_date": "2025-05-01", "txn_type": "income", "amount": 120_000.0, "account_id": 1},
        {"id": 2, "txn_date": "2025-05-06", "txn_type": "expense", "amount": 18_500.0, "account_id": 1},
    ]
    tables = _tables(accounts, txns)
    notes = migrate(tables, from_version=1, today=TODAY)

    implied = ledger.balances(tables["transactions.json"])
    assert round(implied[1], 2) == 130_000.0
    assert round(implied[2], 2) == 2_500.0
    assert 3 not in implied                     # archived accounts are left alone

    opening = [t for t in txns if ledger.has_tag(t.get("tags"), ledger.OPENING_TAG)]
    assert len(opening) == 1
    assert opening[0]["txn_date"] == "2025-05-01"   # not after the earliest entry
    assert all(t["txn_type"] == "adjustment" for t in txns[2:])
    assert len({t["id"] for t in txns}) == len(txns)  # unique ids
    assert notes


def test_v2_never_changes_balances():
    accounts = [{"id": 1, "name": "A", "is_active": 1, "opening_balance": 10.0,
                 "current_balance": 3.0}]
    tables = _tables(accounts, [])
    migrate(tables, from_version=1, today=TODAY)
    assert accounts[0]["current_balance"] == 3.0


def test_newer_store_is_refused():
    with pytest.raises(StoreVersionError):
        migrate({}, from_version=STORE_VERSION + 1, today=TODAY)
