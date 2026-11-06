"""Tests for IncomeSourceService: CRUD validation + delegation to IncomeService."""
from __future__ import annotations

import pytest

from db.connection import Database
from models.account import Account
from models.income import IncomeSource
from repositories.account_repo import AccountRepository
from repositories.income_entry_repo import IncomeEntryRepository
from repositories.income_repo import IncomeRepository
from repositories.transaction_repo import TransactionRepository
from services.income_service import IncomeService
from services.income_source_service import IncomeSourceService
from services.transaction_service import TransactionService


def _service(db: Database) -> IncomeSourceService:
    source_repo = IncomeRepository(db)
    entry_repo = IncomeEntryRepository(db)
    account_repo = AccountRepository(db)
    txn_service = TransactionService(TransactionRepository(db), account_repo)
    income_service = IncomeService(source_repo, entry_repo, txn_service)
    return IncomeSourceService(source_repo, entry_repo, income_service)


def test_create_requires_name(temp_db: Database):
    svc = _service(temp_db)
    with pytest.raises(ValueError):
        svc.create(IncomeSource(name=""))


def test_create_list_toggle_delete(temp_db: Database):
    svc = _service(temp_db)
    source_id = svc.create(IncomeSource(name="Freelance", source_type="freelance", is_active=1))

    active = svc.list_active()
    assert any(s.id == source_id for s in active)

    source = svc.get(source_id)
    svc.toggle_active(source)
    assert svc.get(source_id).is_active == 0

    svc.delete(source_id)
    assert svc.get(source_id) is None


def test_record_month_delegates_and_posts_to_ledger(temp_db: Database):
    svc = _service(temp_db)
    account_id = AccountRepository(temp_db).insert(
        Account(name="Salary AC", account_type="salary", current_balance=0.0)
    )
    source_id = svc.create(
        IncomeSource(name="Acme", source_type="salary", expected_amount=80_000.0,
                      frequency="monthly", deposit_account_id=account_id)
    )
    source = svc.get(source_id)

    entry = svc.record_month(
        source, period_month="2026-05", actual_amount=80_000.0,
        received_date="2026-05-28", account_id=account_id, post_to_ledger=True,
    )
    assert entry.id is not None
    assert svc.has_logged(source_id, "2026-05")
    assert svc.total_received("2026-05") == 80_000.0
    assert len(svc.list_entries(source_id)) == 1

    # Ledger effect: account balance increased by the actual amount.
    account = AccountRepository(temp_db).get_by_id(account_id)
    assert account.current_balance == 80_000.0


def test_net_gross_deductions_delegation(temp_db: Database):
    svc = _service(temp_db)
    source = IncomeSource(
        name="Salary", source_type="salary",
        basic=50_000.0, hra=20_000.0, special_allow=10_000.0,
        pf_employee=1_800.0, professional_tax=200.0, tds=5_000.0,
    )
    assert svc.gross_monthly(source) == 80_000.0
    assert svc.deductions_monthly(source) == 7_000.0
    assert svc.net_monthly(source) == 73_000.0
    assert svc.is_recurring_monthly(source) is True


def test_update_requires_id_and_name(temp_db: Database):
    svc = _service(temp_db)
    with pytest.raises(ValueError):
        svc.update(IncomeSource(name="No id"))

    source_id = svc.create(IncomeSource(name="Side gig"))
    source = svc.get(source_id)
    source.name = ""
    with pytest.raises(ValueError):
        svc.update(source)
