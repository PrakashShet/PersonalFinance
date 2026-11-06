"""Transaction repository smoke tests."""
from __future__ import annotations

from models.account import Account
from models.transaction import Transaction
from repositories.account_repo import AccountRepository
from repositories.transaction_repo import TransactionRepository


def test_transaction_repo_list_filtered(temp_db):
    account_repo = AccountRepository(temp_db)
    account_id = account_repo.insert(
        Account(name="Main", account_type="savings", current_balance=0.0)
    )
    txn_repo = TransactionRepository(temp_db)
    txn_repo.insert(
        Transaction(
            txn_date="2026-05-01",
            txn_type="income",
            amount=100.0,
            account_id=account_id,
            description="Test income",
        )
    )
    rows = txn_repo.list_filtered(year="2026", month="05")
    assert len(rows) == 1
    assert rows[0]["description"] == "Test income"
