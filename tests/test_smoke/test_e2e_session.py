"""End-to-end smoke: bootstrap, mutate data, persist, reload — no UI."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from config.settings import settings
from db.connection import Database
from db.migrate import run_migrations
from models.account import Account
from models.income import IncomeSource
from models.transaction import Transaction
from repositories.account_repo import AccountRepository
from repositories.category_repo import CategoryRepository
from repositories.income_entry_repo import IncomeEntryRepository
from repositories.income_repo import IncomeRepository
from repositories.transaction_repo import TransactionRepository
from services.account_service import AccountService
from services.data_loader import DataLoader
from services.data_persister import DataPersister
from services.income_service import IncomeService
from services.transaction_service import TransactionService
from tests.conftest import SCHEMA_PATH

pytestmark = pytest.mark.smoke


def _wire_services(db: Database):
    account_repo = AccountRepository(db)
    txn_service = TransactionService(TransactionRepository(db), account_repo)
    account_service = AccountService(
        account_repo, txn_service, CategoryRepository(db)
    )
    income_service = IncomeService(
        IncomeRepository(db),
        IncomeEntryRepository(db),
        txn_service,
    )
    return account_repo, account_service, txn_service, income_service


def test_full_session_persist_and_reload(bootstrapped_session):
    """Account + transaction + income survive dump → fresh DB → reload."""
    db, store = bootstrapped_session
    account_repo, account_service, txn_service, income_service = _wire_services(db)

    # 1. Create account with opening balance (posts ledger entry)
    account_id = account_service.create_account(
        Account(
            name="Smoke Savings",
            account_type="savings",
            opening_balance=25_000.0,
            current_balance=25_000.0,
        )
    )

    # 2. Record an expense
    txn_service.create_transaction(
        Transaction(
            txn_date="2026-05-28",
            txn_type="expense",
            amount=2_000.0,
            account_id=account_id,
            description="Smoke test expense",
        )
    )

    # 3. Record monthly income
    income_repo = IncomeRepository(db)
    source_id = income_repo.insert(
        IncomeSource(
            name="Smoke Salary",
            source_type="salary",
            expected_amount=60_000.0,
            frequency="monthly",
            deposit_account_id=account_id,
        )
    )
    source = income_repo.get_by_id(source_id)
    income_service.record_month(
        source,
        period_month="2026-05",
        actual_amount=60_000.0,
        received_date="2026-05-28",
        account_id=account_id,
        post_to_ledger=True,
    )

    expected_balance = 25_000.0 - 2_000.0 + 60_000.0
    assert account_repo.get_by_id(account_id).current_balance == expected_balance

    # 4. Persist to JSON store (no backup — isolated tmp dir)
    DataPersister(db).dump_store_data(store, make_backup=False)
    db.close()

    # 5. Fresh DB + reload from disk
    db2 = Database()
    db2.connect(store.parent / "reloaded.db")
    db2.apply_schema(SCHEMA_PATH)
    run_migrations(db2)
    DataLoader(db2).load_store_data(store)

    accounts = json.loads((store / "accounts.json").read_text(encoding="utf-8"))
    txns = json.loads((store / "transactions.json").read_text(encoding="utf-8"))
    entries = json.loads((store / "income_entries.json").read_text(encoding="utf-8"))

    assert any(a["name"] == "Smoke Savings" for a in accounts)
    assert len(txns) >= 3  # opening + expense + income
    assert len(entries) == 1

    reloaded = AccountRepository(db2).get_by_id(account_id)
    assert reloaded is not None
    assert reloaded.current_balance == expected_balance
    db2.close()


def test_bootstrap_matches_main_flow(tmp_path: Path, empty_store: Path):
    """Smoke-check that loader + migrations produce queryable schema."""
    db = Database()
    db.connect(tmp_path / "boot.db")
    db.apply_schema(SCHEMA_PATH)
    run_migrations(db)

    loader = DataLoader(db)
    loader.load_seed_data(settings.SEED_DIR)
    loader.load_store_data(empty_store)

    categories = db.fetch_all("SELECT id FROM categories")
    assert len(categories) > 0

    tables = db.fetch_all(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    table_names = {r["name"] for r in tables}
    assert "accounts" in table_names
    assert "transactions" in table_names
    db.close()
