"""Account creation posts an opening-balance ledger entry."""
from __future__ import annotations

from db.connection import Database
from models.account import Account
from repositories.account_repo import AccountRepository
from repositories.category_repo import CategoryRepository
from repositories.transaction_repo import TransactionRepository
from services.account_service import AccountService
from services.transaction_service import TransactionService


def test_create_account_posts_opening_balance_transaction(temp_db: Database):
    account_repo = AccountRepository(temp_db)
    txn_service = TransactionService(TransactionRepository(temp_db), account_repo)
    service = AccountService(
        account_repo, txn_service, CategoryRepository(temp_db)
    )

    account_id = service.create_account(
        Account(
            name="Test Savings",
            account_type="savings",
            opening_balance=10_000.0,
            current_balance=10_000.0,
        )
    )

    acct = account_repo.get_by_id(account_id)
    assert acct is not None
    assert acct.current_balance == 10_000.0

    txns = temp_db.fetch_all(
        "SELECT * FROM transactions WHERE account_id = ?", (account_id,)
    )
    assert len(txns) == 1
    assert txns[0]["txn_type"] == "income"
    assert txns[0]["amount"] == 10_000.0
    assert "Opening balance" in txns[0]["description"]


def test_create_account_zero_balance_skips_transaction(temp_db: Database):
    account_repo = AccountRepository(temp_db)
    service = AccountService(account_repo)

    account_id = service.create_account(
        Account(name="Empty", account_type="cash", current_balance=0.0)
    )

    txns = temp_db.fetch_all(
        "SELECT * FROM transactions WHERE account_id = ?", (account_id,)
    )
    assert txns == []
