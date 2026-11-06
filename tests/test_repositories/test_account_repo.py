"""Repository CRUD smoke tests."""
from __future__ import annotations

from models.account import Account
from repositories.account_repo import AccountRepository


def test_account_repo_insert_and_fetch(temp_db):
    repo = AccountRepository(temp_db)
    account_id = repo.insert(
        Account(name="Test Bank", account_type="savings", current_balance=1_000.0)
    )
    row = repo.get_by_id(account_id)
    assert row is not None
    assert row.name == "Test Bank"
    assert row.current_balance == 1_000.0


def test_account_repo_update_balance(temp_db):
    repo = AccountRepository(temp_db)
    account_id = repo.insert(
        Account(name="Wallet", account_type="cash", current_balance=500.0)
    )
    repo.update_balance(account_id, 250.0)
    assert repo.get_by_id(account_id).current_balance == 750.0
