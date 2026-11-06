"""TransactionService balance side-effects and validation."""
from __future__ import annotations

import pytest

from db.connection import Database
from models.account import Account
from models.transaction import Transaction
from repositories.account_repo import AccountRepository
from repositories.transaction_repo import TransactionRepository
from services.transaction_service import TransactionService


def _svc(db: Database) -> TransactionService:
    account_repo = AccountRepository(db)
    return TransactionService(TransactionRepository(db), account_repo)


def _insert_account(db: Database, name: str, balance: float = 0.0) -> int:
    repo = AccountRepository(db)
    return repo.insert(
        Account(name=name, account_type="savings", current_balance=balance)
    )


def test_expense_decreases_account_balance(temp_db: Database):
    account_id = _insert_account(temp_db, "Wallet", 10_000.0)
    svc = _svc(temp_db)

    svc.create_transaction(
        Transaction(
            txn_date="2026-05-01",
            txn_type="expense",
            amount=2_500.0,
            account_id=account_id,
            description="Groceries",
        )
    )

    acct = AccountRepository(temp_db).get_by_id(account_id)
    assert acct is not None
    assert acct.current_balance == 7_500.0


def test_income_increases_account_balance(temp_db: Database):
    account_id = _insert_account(temp_db, "Salary", 0.0)
    svc = _svc(temp_db)

    svc.create_transaction(
        Transaction(
            txn_date="2026-05-01",
            txn_type="income",
            amount=50_000.0,
            account_id=account_id,
        )
    )

    acct = AccountRepository(temp_db).get_by_id(account_id)
    assert acct is not None
    assert acct.current_balance == 50_000.0


def test_transfer_moves_balance_between_accounts(temp_db: Database):
    from_id = _insert_account(temp_db, "HDFC", 20_000.0)
    to_id = _insert_account(temp_db, "ICICI", 5_000.0)
    svc = _svc(temp_db)

    svc.create_transaction(
        Transaction(
            txn_date="2026-05-01",
            txn_type="transfer",
            amount=3_000.0,
            account_id=from_id,
            counter_account_id=to_id,
        )
    )

    repo = AccountRepository(temp_db)
    assert repo.get_by_id(from_id).current_balance == 17_000.0
    assert repo.get_by_id(to_id).current_balance == 8_000.0


def test_delete_transaction_reverses_balance(temp_db: Database):
    account_id = _insert_account(temp_db, "Cash", 10_000.0)
    svc = _svc(temp_db)
    txn_id = svc.create_transaction(
        Transaction(
            txn_date="2026-05-01",
            txn_type="expense",
            amount=1_000.0,
            account_id=account_id,
        )
    )

    svc.delete_transaction(txn_id)

    acct = AccountRepository(temp_db).get_by_id(account_id)
    assert acct is not None
    assert acct.current_balance == 10_000.0


def test_transfer_requires_distinct_accounts(temp_db: Database):
    account_id = _insert_account(temp_db, "Solo", 1_000.0)
    svc = _svc(temp_db)

    with pytest.raises(ValueError, match="different"):
        svc.create_transaction(
            Transaction(
                txn_date="2026-05-01",
                txn_type="transfer",
                amount=100.0,
                account_id=account_id,
                counter_account_id=account_id,
            )
        )
