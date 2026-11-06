"""Accounts and the ledger: opening balances, balance edits, reconciliation."""
from __future__ import annotations

from db.connection import Database
from models.account import Account
from models.transaction import Transaction
from repositories.account_repo import AccountRepository
from repositories.category_repo import CategoryRepository
from repositories.transaction_repo import TransactionRepository
from services.account_service import AccountService
from services.transaction_service import TransactionService


def _wire(db: Database):
    account_repo = AccountRepository(db)
    txn_service = TransactionService(TransactionRepository(db), account_repo)
    service = AccountService(account_repo, txn_service, CategoryRepository(db))
    return account_repo, txn_service, service


def test_create_account_posts_opening_balance_adjustment(temp_db: Database):
    account_repo, _txn, service = _wire(temp_db)

    account_id = service.create_account(
        Account(name="Test Savings", account_type="savings", current_balance=10_000.0)
    )

    acct = account_repo.get_by_id(account_id)
    assert acct.current_balance == 10_000.0
    assert acct.opening_balance == 10_000.0

    txns = temp_db.fetch_all("SELECT * FROM transactions WHERE account_id = ?", (account_id,))
    assert len(txns) == 1
    # An opening balance is not income.
    assert txns[0]["txn_type"] == "adjustment"
    assert txns[0]["amount"] == 10_000.0
    assert "Opening balance" in txns[0]["description"]


def test_opening_balance_is_not_counted_as_income(temp_db: Database):
    _repo, txn_service, service = _wire(temp_db)
    service.create_account(Account(name="Big", account_type="savings", current_balance=500_000.0))

    summary = txn_service.summary()
    assert summary["income"] == 0.0
    assert summary["net"] == 0.0


def test_create_account_zero_balance_skips_transaction(temp_db: Database):
    account_repo = AccountRepository(temp_db)
    service = AccountService(account_repo)

    account_id = service.create_account(
        Account(name="Empty", account_type="cash", current_balance=0.0)
    )

    txns = temp_db.fetch_all("SELECT * FROM transactions WHERE account_id = ?", (account_id,))
    assert txns == []


def test_editing_balance_posts_adjustment_not_overwrite(temp_db: Database):
    account_repo, txn_service, service = _wire(temp_db)
    aid = service.create_account(Account(name="Wallet", account_type="wallet", current_balance=1_000.0))

    acct = account_repo.get_by_id(aid)
    acct.current_balance = 1_250.0
    service.update_account(acct)

    assert account_repo.get_by_id(aid).current_balance == 1_250.0
    rows = temp_db.fetch_all(
        "SELECT amount, description FROM transactions WHERE account_id = ? ORDER BY id", (aid,))
    assert [r["amount"] for r in rows] == [1_000.0, 250.0]
    assert "Balance adjustment" in rows[1]["description"]
    # The ledger still explains the balance.
    assert service.reconciliation_report() == []


def test_deleting_an_old_entry_after_a_balance_edit_stays_consistent(temp_db: Database):
    """The bug the adjustment model fixes: a hand-set balance plus a later
    delete of an old entry used to leave the balance wrong."""
    account_repo, txn_service, service = _wire(temp_db)
    aid = service.create_account(Account(name="Bank", account_type="savings", current_balance=10_000.0))
    rent = txn_service.create_transaction(Transaction(
        txn_date="2026-01-05", txn_type="expense", amount=4_000.0, account_id=aid))
    service.set_balance(aid, 7_000.0)          # user corrects the balance by hand

    txn_service.delete_transaction(rent)       # then removes the old rent entry
    assert account_repo.get_by_id(aid).current_balance == 11_000.0
    assert service.reconciliation_report() == []


def test_reconciliation_report_and_reconcile(temp_db: Database):
    account_repo, txn_service, service = _wire(temp_db)
    aid = service.create_account(Account(name="Bank", account_type="savings", current_balance=5_000.0))
    # Simulate a balance edited outside the ledger (e.g. JSON edited by hand).
    account_repo.update_balance(aid, 700.0)

    report = service.reconciliation_report()
    assert len(report) == 1
    assert report[0].difference == 700.0

    assert service.reconcile(aid) == 700.0
    assert account_repo.get_by_id(aid).current_balance == 5_700.0   # unchanged
    assert service.reconciliation_report() == []


def test_adjustments_excluded_from_income_and_expense(temp_db: Database):
    _repo, txn_service, service = _wire(temp_db)
    aid = service.create_account(Account(name="Bank", account_type="savings", current_balance=1_000.0))
    txn_service.create_adjustment(aid, -300.0, "Correction")
    txn_service.create_transaction(Transaction(
        txn_date="2026-02-01", txn_type="expense", amount=100.0, account_id=aid))

    s = txn_service.summary()
    assert s["expense"] == 100.0
    assert s["income"] == 0.0
