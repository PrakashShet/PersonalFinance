"""RecurringService: what's due, and one-step logging that updates the source."""
from __future__ import annotations

from datetime import date

from models.account import Account
from models.holding import Holding
from models.liability import Liability
from repositories.account_repo import AccountRepository
from repositories.category_repo import CategoryRepository
from repositories.holding_repo import HoldingRepository
from repositories.liability_repo import LiabilityRepository
from repositories.reference_repos import ReminderRepository
from repositories.transaction_repo import TransactionRepository
from services.recurring_service import (
    KIND_EMI,
    KIND_PREMIUM,
    KIND_SIP,
    RecurringService,
    add_months,
)
from services.transaction_service import TransactionService

TODAY = date(2026, 11, 6)


def _wire(db):
    accounts = AccountRepository(db)
    txn = TransactionService(TransactionRepository(db), accounts)
    svc = RecurringService(txn, HoldingRepository(db), LiabilityRepository(db),
                           ReminderRepository(db), CategoryRepository(db))
    bank = accounts.insert(Account(name="Bank", account_type="savings", current_balance=100_000.0))
    return svc, accounts, bank


def test_add_months_clamps_to_month_end():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 11, 15), 12) == date(2027, 11, 15)


def test_sip_is_due_once_and_logging_updates_holding(temp_db):
    svc, accounts, bank = _wire(temp_db)
    holdings = HoldingRepository(temp_db)
    hid = holdings.insert(Holding(name="Flexi Cap", holding_type="sip", invested_amount=50_000.0,
                                  current_value=60_000.0, sip_amount=5_000.0, sip_day_of_month=5,
                                  linked_account_id=bank, quantity=100.0, current_price=600.0))

    items = [i for i in svc.due_items(TODAY) if i.kind == KIND_SIP]
    assert len(items) == 1
    item = items[0]
    assert item.overdue                      # the 5th has passed
    assert item.account_id == bank

    svc.log(item, 5_000.0, "2026-11-05", bank)

    h = holdings.get_by_id(hid)
    assert h.invested_amount == 55_000.0
    assert h.current_value == 65_000.0
    assert round(h.quantity, 4) == round(100 + 5_000 / 600, 4)
    assert accounts.get_by_id(bank).current_balance == 95_000.0
    # Logged: not offered again this month.
    assert not [i for i in svc.due_items(TODAY) if i.kind == KIND_SIP]


def test_emi_logging_reduces_outstanding_and_moves_due_date(temp_db):
    svc, accounts, bank = _wire(temp_db)
    loans = LiabilityRepository(temp_db)
    lid = loans.insert(Liability(name="Car", liability_type="car_loan", principal=500_000.0,
                                 outstanding=300_000.0, interest_rate=12.0, emi_amount=10_000.0,
                                 remaining_months=36, next_due_date="2026-11-10", account_id=bank))

    item = next(i for i in svc.due_items(TODAY) if i.kind == KIND_EMI)
    svc.log(item, 10_000.0, "2026-11-10", bank)

    lb = loans.get_by_id(lid)
    interest = 300_000.0 * 12.0 / 1200.0                 # 3,000
    assert lb.outstanding == 300_000.0 - (10_000.0 - interest)
    assert lb.remaining_months == 35
    assert lb.next_due_date == "2026-12-10"
    assert not [i for i in svc.due_items(TODAY) if i.kind == KIND_EMI]
    row = temp_db.fetch_one("SELECT tags, txn_type FROM transactions WHERE tags LIKE 'emi:%'")
    assert row["txn_type"] == "expense"


def test_premium_moves_a_year(temp_db):
    svc, _accounts, bank = _wire(temp_db)
    holdings = HoldingRepository(temp_db)
    hid = holdings.insert(Holding(name="Term plan", holding_type="term_insurance",
                                  premium_amount=18_000.0, premium_due_date="2026-11-15",
                                  sum_assured=10_000_000.0))
    item = next(i for i in svc.due_items(TODAY) if i.kind == KIND_PREMIUM)
    assert not item.overdue
    svc.log(item, 18_000.0, "2026-11-15", bank)
    assert holdings.get_by_id(hid).premium_due_date == "2027-11-15"


def test_far_future_items_are_not_listed(temp_db):
    svc, _accounts, bank = _wire(temp_db)
    LiabilityRepository(temp_db).insert(Liability(
        name="Home", liability_type="home_loan", principal=1.0, outstanding=1.0,
        emi_amount=100.0, next_due_date="2027-03-01", account_id=bank))
    assert not [i for i in svc.due_items(TODAY) if i.kind == KIND_EMI]


def test_reminders_round_trip(temp_db):
    svc, _accounts, _bank = _wire(temp_db)
    rid = svc.add_reminder("Renew car insurance", "2026-11-08", 9_500.0)
    items = [i for i in svc.due_items(TODAY) if i.ref_id == rid and i.kind == "reminder"]
    assert len(items) == 1
    svc.complete_reminder(rid)
    assert not [i for i in svc.due_items(TODAY) if i.kind == "reminder"]
