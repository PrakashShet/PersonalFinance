"""BudgetService: monthly / yearly limits per expense category.

Numbers are worked by hand in the comments, not read back from the code.
"""
from __future__ import annotations

from datetime import date

import pytest

from models.account import Account
from models.transaction import Transaction
from repositories.account_repo import AccountRepository
from repositories.budget_repo import BudgetRepository
from repositories.category_repo import CategoryRepository
from repositories.reference_repos import FxRateRepository
from repositories.transaction_repo import TransactionRepository
from services.budget_service import (
    MONTHLY,
    STATE_NEAR,
    STATE_OK,
    STATE_OVER,
    YEARLY,
    BudgetService,
    period_bounds,
    period_label,
    typical_spend,
)
from services.fx_service import FxService
from services.preferences_service import PreferencesService
from services.transaction_service import TransactionService

TODAY = date(2026, 11, 6)


class _World:
    def __init__(self, db) -> None:
        self.accounts = AccountRepository(db)
        self.cats = CategoryRepository(db)
        self.fx = FxService(FxRateRepository(db))
        self.prefs = PreferencesService(None)
        self.topics: list[str] = []
        self.txns = TransactionService(TransactionRepository(db), self.accounts)
        self.svc = BudgetService(BudgetRepository(db), TransactionRepository(db), self.cats,
                                 fx_service=self.fx, preferences=self.prefs,
                                 on_change=self.topics.append)
        self.bank = self.accounts.insert(Account(name="Bank", account_type="savings",
                                                 current_balance=1_000_000.0))
        self.food = self.cats.ensure("Food & Dining", "expense")
        self.travel = self.cats.ensure("Travel", "expense")
        self.groceries = self.cats.ensure("Groceries", "expense")
        self.salary = self.cats.ensure("Salary", "income")

    def spend(self, when: str, amount: float, category_id=None, account_id=None,
              txn_type: str = "expense") -> int:
        return self.txns.create_transaction(Transaction(
            txn_date=when, txn_type=txn_type, amount=amount,
            account_id=account_id or self.bank, category_id=category_id))


@pytest.fixture
def w(temp_db) -> _World:
    return _World(temp_db)


def _november(w: _World) -> None:
    w.spend("2026-10-31", 2_000.0, w.food)          # last month
    w.spend("2026-11-01", 3_000.0, w.food)
    w.spend("2026-11-05", 4_500.0, w.food)
    w.spend("2026-11-03", 1_000.0, w.groceries)     # other category
    w.spend("2026-11-01", 50_000.0, w.salary, txn_type="income")
    w.spend("2026-11-02", 700.0, None)              # uncategorised


# ---------------------------------------------------------------- periods
def test_period_bounds_month_and_both_year_starts():
    assert period_bounds(MONTHLY, date(2028, 2, 10)) == (date(2028, 2, 1), date(2028, 2, 29))
    assert period_bounds(MONTHLY, date(2026, 12, 31)) == (date(2026, 12, 1), date(2026, 12, 31))
    assert period_bounds(YEARLY, date(2026, 3, 31), 1) == (date(2026, 1, 1), date(2026, 12, 31))
    # Indian financial year: 31 March belongs to the year that began the April before.
    assert period_bounds(YEARLY, date(2026, 3, 31), 4) == (date(2025, 4, 1), date(2026, 3, 31))
    assert period_bounds(YEARLY, date(2026, 4, 1), 4) == (date(2026, 4, 1), date(2027, 3, 31))


def test_period_labels():
    assert period_label(MONTHLY, date(2026, 11, 1)) == "November 2026"
    assert period_label(MONTHLY, date(2026, 11, 1), short=True) == "Nov 2026"
    assert period_label(YEARLY, date(2026, 1, 1)) == "2026"
    assert period_label(YEARLY, date(2026, 4, 1)) == "FY 2026–27"


# ------------------------------------------------------------------- CRUD
def test_set_limit_creates_then_replaces_never_duplicates(w):
    first = w.svc.set_limit(w.food, MONTHLY, 10_000)
    again = w.svc.set_limit(w.food, MONTHLY, 12_000, notes="Swiggy too")
    assert again == first
    assert [(b.period, b.amount, b.notes) for b in w.svc.list_all()] == [(MONTHLY, 12_000.0, "Swiggy too")]
    yearly = w.svc.set_limit(w.food, YEARLY, 1_00_000)
    assert yearly != first and len(w.svc.list_all()) == 2
    assert w.topics.count("budgets") == 3


@pytest.mark.parametrize("period,amount,which", [
    ("weekly", 1_000, "food"), (MONTHLY, 0, "food"), (MONTHLY, -5, "food"),
    (MONTHLY, 1_000, "salary"), (MONTHLY, 1_000, None),
])
def test_invalid_limits_are_refused(w, period, amount, which):
    category = {"food": w.food, "salary": w.salary, None: 9_999}[which]
    with pytest.raises(ValueError):
        w.svc.set_limit(category, period, amount)
    assert w.svc.list_all() == []


def test_update_keeps_created_at_and_refuses_a_clash(w):
    monthly = w.svc.set_limit(w.food, MONTHLY, 10_000)
    yearly = w.svc.set_limit(w.food, YEARLY, 1_00_000)
    created = w.svc.get(yearly).created_at
    b = w.svc.get(yearly)
    b.amount = 90_000
    w.svc.update(b)
    assert w.svc.get(yearly).amount == 90_000.0
    assert w.svc.get(yearly).created_at == created
    b.period = MONTHLY                                  # Food already has a monthly limit
    with pytest.raises(ValueError, match="already has a monthly limit"):
        w.svc.update(b)
    w.svc.delete(monthly)
    w.svc.update(b)                                     # now it can become monthly
    assert [x.period for x in w.svc.list_all()] == [MONTHLY]


# ----------------------------------------------------------------- status
def test_monthly_status_counts_only_this_category_this_month(w):
    _november(w)
    w.svc.set_limit(w.food, MONTHLY, 10_000)
    [s] = w.svc.statuses(TODAY)
    # 3,000 + 4,500 in November; October's 2,000, groceries, salary, uncategorised excluded.
    assert s.spent == 7_500.0
    assert s.remaining == 2_500.0
    assert s.pct == 75.0 and s.state == STATE_OK
    assert (s.start, s.end, s.label) == (date(2026, 11, 1), date(2026, 11, 30), "November 2026")
    assert s.days_left == 25                            # 6th to 30th, today included
    assert s.allowance() == 100.0                       # 2,500 / 25 days


def test_states_near_and_over(w):
    _november(w)
    budget = w.svc.set_limit(w.food, MONTHLY, 10_000)
    w.spend("2026-11-06", 1_000.0, w.food)              # 8,500 = 85 %
    assert w.svc.status(budget, TODAY).state == STATE_NEAR
    w.spend("2026-11-06", 2_000.0, w.food)              # 10,500
    s = w.svc.status(budget, TODAY)
    assert s.state == STATE_OVER and s.remaining == -500.0 and s.allowance() is None
    assert [a.budget.id for a in w.svc.alerts(TODAY)] == [budget]


def test_exactly_at_the_limit_is_near_not_over(w):
    w.spend("2026-11-02", 5_000.0, w.food)
    budget = w.svc.set_limit(w.food, MONTHLY, 5_000)
    assert w.svc.status(budget, TODAY).state == STATE_NEAR


def test_yearly_status_follows_the_year_start_setting(w):
    w.spend("2026-02-10", 30_000.0, w.travel)
    w.spend("2026-05-20", 50_000.0, w.travel)
    budget = w.svc.set_limit(w.travel, YEARLY, 1_20_000)

    s = w.svc.status(budget, TODAY)                     # calendar year 2026
    assert (s.label, s.spent, s.months_left) == ("2026", 80_000.0, 2)

    w.svc.set_year_start(4)                             # April - March
    assert w.prefs.get("budget_year_start") == 4
    s = w.svc.status(budget, TODAY)                     # FY 2026-27 starts 1 Apr 2026
    assert (s.label, s.spent, s.months_left) == ("FY 2026–27", 50_000.0, 5)
    assert s.allowance() == 14_000.0                    # 70,000 left / 5 months
    with pytest.raises(ValueError):
        w.svc.set_year_start(7)


def test_foreign_spending_needs_a_rate(w):
    usd = w.accounts.insert(Account(name="Chase", account_type="savings", currency="USD",
                                    current_balance=5_000.0))
    w.spend("2026-11-02", 1_000.0, w.food)
    w.spend("2026-11-03", 100.0, w.food, account_id=usd)
    budget = w.svc.set_limit(w.food, MONTHLY, 10_000)

    s = w.svc.status(budget, TODAY)
    assert s.spent == 1_000.0                           # dollars never added as rupees
    assert s.unconverted == {"USD": 100.0}

    w.fx.set_rate("USD", 83.0)
    s = w.svc.status(budget, TODAY)
    assert s.spent == 1_000.0 + 8_300.0 and s.unconverted == {}


# ---------------------------------------------------------------- impact
def test_impact_previews_an_expense_and_skips_the_entry_being_edited(w):
    _november(w)
    w.svc.set_limit(w.food, MONTHLY, 10_000)
    [imp] = w.svc.impact(w.food, "2026-11-06", 1_000.0, today=TODAY)
    assert imp.status.spent == 7_500.0 and imp.added == 1_000.0
    assert imp.remaining_after == 1_500.0 and imp.state_after == STATE_NEAR

    edited = w.spend("2026-11-06", 4_000.0, w.food)     # now 11,500 - over
    [imp] = w.svc.impact(w.food, "2026-11-06", 4_000.0, exclude_txn_id=edited, today=TODAY)
    assert imp.status.spent == 7_500.0 and imp.state_after == STATE_OVER   # not 15,500
    [imp] = w.svc.impact(w.food, "2026-11-06", 1_000.0, exclude_txn_id=edited, today=TODAY)
    assert imp.state_after == STATE_NEAR                # editing it down to 1,000 -> 8,500

    # An expense dated in October is checked against October's limit.
    [imp] = w.svc.impact(w.food, "2026-10-15", 500.0, today=TODAY)
    assert imp.status.label == "October 2026" and imp.status.spent == 2_000.0

    assert w.svc.impact(w.groceries, "2026-11-06", 100.0, today=TODAY) == []
    assert w.svc.impact(None, "2026-11-06", 100.0, today=TODAY) == []


def test_impact_without_a_rate_reports_none(w):
    w.svc.set_limit(w.food, MONTHLY, 10_000)
    [imp] = w.svc.impact(w.food, "2026-11-06", 50.0, currency="USD", today=TODAY)
    assert imp.added is None and imp.spent_after == 0.0


# ------------------------------------------------------- history & advice
def test_history_and_typical_spend(w):
    _november(w)
    budget = w.svc.set_limit(w.food, MONTHLY, 10_000)
    hist = w.svc.history(budget, periods=3, today=TODAY)
    assert [(p.label, p.spent, p.current, p.logged) for p in hist] == [
        ("Sep 2026", 0.0, False, False),                 # nothing logged at all
        ("Oct 2026", 2_000.0, False, True),
        ("Nov 2026", 7_500.0, True, True),
    ]
    assert typical_spend(hist) == 2_000.0               # only October counts


def test_suggestion_uses_months_with_logged_spending(w):
    w.spend("2026-08-10", 3_000.0, w.food)
    w.spend("2026-10-10", 4_100.0, w.food)
    w.spend("2026-11-02", 9_999.0, w.food)              # current month - ignored
    s = w.svc.suggestion(w.food, MONTHLY, today=TODAY)
    # Aug + Oct logged (Sep empty): 7,100 / 2 = 3,550 -> rounded up to 3,600
    assert (s.amount, s.months) == (3_600.0, 2)
    y = w.svc.suggestion(w.food, YEARLY, today=TODAY)
    assert (y.amount, y.months) == (42_600.0, 2)        # 3,550 x 12
    assert w.svc.suggestion(w.travel, MONTHLY, today=TODAY) is None


def test_unbudgeted_lists_spending_without_any_limit(w):
    _november(w)
    w.svc.set_limit(w.food, YEARLY, 1_00_000)           # a yearly limit counts as budgeted
    assert [(u.name, u.spent) for u in w.svc.unbudgeted(TODAY)] == [
        ("Groceries", 1_000.0), ("Uncategorised", 700.0)]


def test_totals_by_period(w):
    _november(w)
    w.svc.set_limit(w.food, MONTHLY, 10_000)
    w.svc.set_limit(w.groceries, MONTHLY, 5_000)
    w.svc.set_limit(w.travel, YEARLY, 50_000)
    statuses = w.svc.statuses(TODAY)
    m = w.svc.totals(statuses, MONTHLY)
    assert (m.count, m.limit, m.spent, m.remaining) == (2, 15_000.0, 8_500.0, 6_500.0)
    assert w.svc.totals(statuses, YEARLY).count == 1
