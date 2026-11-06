"""IncomeService monthly recording and ledger posting."""
from __future__ import annotations

from db.connection import Database
from models.account import Account
from models.income import IncomeSource
from repositories.account_repo import AccountRepository
from repositories.income_entry_repo import IncomeEntryRepository
from repositories.income_repo import IncomeRepository
from repositories.transaction_repo import TransactionRepository
from services.income_service import IncomeService
from services.transaction_service import TransactionService


def test_record_month_posts_income_and_updates_balance(temp_db: Database):
    account_repo = AccountRepository(temp_db)
    account_id = account_repo.insert(
        Account(name="Salary AC", account_type="salary", current_balance=0.0)
    )

    income_repo = IncomeRepository(temp_db)
    source_id = income_repo.insert(
        IncomeSource(
            name="Acme Corp",
            source_type="salary",
            expected_amount=80_000.0,
            frequency="monthly",
            deposit_account_id=account_id,
        )
    )
    source = income_repo.get_by_id(source_id)
    assert source is not None

    txn_service = TransactionService(TransactionRepository(temp_db), account_repo)
    income_service = IncomeService(
        income_repo, IncomeEntryRepository(temp_db), txn_service
    )

    entry = income_service.record_month(
        source,
        period_month="2026-05",
        actual_amount=75_000.0,
        received_date="2026-05-28",
        account_id=account_id,
        post_to_ledger=True,
    )

    assert entry.id is not None
    assert entry.transaction_id is not None
    assert entry.actual_amount == 75_000.0

    acct = account_repo.get_by_id(account_id)
    assert acct is not None
    assert acct.current_balance == 75_000.0

    txns = temp_db.fetch_all("SELECT * FROM transactions WHERE id = ?", (entry.transaction_id,))
    assert len(txns) == 1
    assert txns[0]["txn_type"] == "income"
    assert txns[0]["income_source_id"] == source_id


def test_record_month_without_ledger_skips_transaction(temp_db: Database):
    account_repo = AccountRepository(temp_db)
    account_id = account_repo.insert(
        Account(name="Cash", account_type="cash", current_balance=1_000.0)
    )

    income_repo = IncomeRepository(temp_db)
    source_id = income_repo.insert(
        IncomeSource(name="Side gig", source_type="freelance", frequency="irregular")
    )
    source = income_repo.get_by_id(source_id)
    assert source is not None

    txn_service = TransactionService(TransactionRepository(temp_db), account_repo)
    income_service = IncomeService(
        income_repo, IncomeEntryRepository(temp_db), txn_service
    )

    entry = income_service.record_month(
        source,
        period_month="2026-05",
        actual_amount=5_000.0,
        account_id=account_id,
        post_to_ledger=False,
    )

    assert entry.transaction_id is None
    assert account_repo.get_by_id(account_id).current_balance == 1_000.0
    assert temp_db.fetch_all("SELECT id FROM transactions") == []
