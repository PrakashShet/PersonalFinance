"""Budgets - a spending limit for an expense category, per month or per year.

What counts as spending: ``expense`` transactions in the budget's category
during the period. Transfers, investments and balance adjustments never count.
Amounts paid from accounts in other currencies are converted with ``fx_rates``;
spending in a currency without a rate is reported in ``unconverted`` and never
added as if it were rupees (the same rule as net worth).

Periods: a month is a calendar month. A year starts in the month held by the
``budget_year_start`` preference - 1 (January) or 4 (April, the Indian
financial year). A budget matches a transaction's own category only.

A category has at most one monthly and one yearly limit (``UNIQUE`` in the
schema); :meth:`BudgetService.set_limit` replaces an existing one.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, Optional

from models.budget import Budget
from repositories.budget_repo import BudgetRepository
from repositories.category_repo import CategoryRepository
from repositories.transaction_repo import TransactionRepository
from services.preferences_service import PreferencesService
from utils.logger import get_logger

log = get_logger(__name__)

MONTHLY = "monthly"
YEARLY = "yearly"
PERIODS = (MONTHLY, YEARLY)
YEAR_STARTS = (1, 4)            # January, or April (Indian financial year)
NEAR_PCT = 80.0                 # "near the limit" from this share of it
STATE_OK, STATE_NEAR, STATE_OVER = "ok", "near", "over"
_CENT = 0.005


# --------------------------------------------------------------------------
# periods (pure)
# --------------------------------------------------------------------------

def _month_start(year: int, month: int, shift: int = 0) -> date:
    total = year * 12 + (month - 1) + shift
    return date(total // 12, total % 12 + 1, 1)


def period_bounds(period: str, on: date, year_start: int = 1) -> tuple[date, date]:
    """First and last day (inclusive) of the ``period`` that contains ``on``."""
    if period == MONTHLY:
        return date(on.year, on.month, 1), _month_start(on.year, on.month, 1) - timedelta(days=1)
    if period == YEARLY:
        year = on.year if on.month >= year_start else on.year - 1
        return date(year, year_start, 1), _month_start(year, year_start, 12) - timedelta(days=1)
    raise ValueError(f"Unknown budget period: {period!r}")


def period_label(period: str, start: date, short: bool = False) -> str:
    """'November 2026' ('Nov 2026' short), '2026', or 'FY 2026–27'."""
    if period == MONTHLY:
        return start.strftime("%b %Y" if short else "%B %Y")
    if start.month == 1:
        return str(start.year)
    if start.month == 4:
        return f"FY {start.year}–{(start.year + 1) % 100:02d}"
    end = _month_start(start.year, start.month, 11)
    return f"{start:%b %Y} – {end:%b %Y}"


def budget_state(spent: float, limit: float) -> str:
    if spent - limit > _CENT:
        return STATE_OVER
    if limit > 0 and spent / limit * 100.0 >= NEAR_PCT:
        return STATE_NEAR
    return STATE_OK


def _as_date(value) -> Optional[date]:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _round_up(amount: float, step: float = 100.0) -> float:
    return float(math.ceil(amount / step) * step)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------

@dataclass
class BudgetStatus:
    """One budget over one period: what was spent and what is left."""

    budget: Budget
    category_name: str
    start: date
    end: date                                    # inclusive
    spent: float                                 # rupees
    today: date
    unconverted: dict[str, float] = field(default_factory=dict)   # currency -> amount

    @property
    def period(self) -> str:
        return self.budget.period

    @property
    def limit(self) -> float:
        return float(self.budget.amount or 0.0)

    @property
    def remaining(self) -> float:
        return self.limit - self.spent

    @property
    def pct(self) -> float:
        if self.limit <= 0:
            return 0.0 if self.spent <= _CENT else 100.0
        return self.spent / self.limit * 100.0

    @property
    def state(self) -> str:
        return budget_state(self.spent, self.limit)

    @property
    def label(self) -> str:
        return period_label(self.period, self.start)

    @property
    def is_current(self) -> bool:
        return self.start <= self.today <= self.end

    @property
    def days_left(self) -> int:
        """Days left in the period, today included (0 once it has ended)."""
        if self.today > self.end:
            return 0
        return (self.end - max(self.today, self.start)).days + 1

    @property
    def months_left(self) -> int:
        """Calendar months left in the period, this one included."""
        if self.today > self.end:
            return 0
        ref = max(self.today, self.start)
        return (self.end.year - ref.year) * 12 + self.end.month - ref.month + 1

    def allowance(self) -> Optional[float]:
        """What is left per remaining day (monthly) or month (yearly)."""
        if self.remaining <= _CENT:
            return None
        n = self.days_left if self.period == MONTHLY else self.months_left
        return self.remaining / n if n > 0 else None


@dataclass
class BudgetImpact:
    """How one expense being entered would leave a budget."""

    status: BudgetStatus          # without the expense (and without the entry being edited)
    added: Optional[float]        # the expense in rupees; None = its currency has no rate

    @property
    def spent_after(self) -> float:
        return self.status.spent + (self.added or 0.0)

    @property
    def remaining_after(self) -> float:
        return self.status.limit - self.spent_after

    @property
    def state_after(self) -> str:
        return budget_state(self.spent_after, self.status.limit)


@dataclass
class PeriodSpend:
    start: date
    end: date
    label: str
    spent: float
    limit: float
    current: bool
    logged: bool          # any spending at all was recorded in this period

    @property
    def pct(self) -> float:
        return self.spent / self.limit * 100.0 if self.limit > 0 else 0.0

    @property
    def state(self) -> str:
        return budget_state(self.spent, self.limit)


@dataclass
class UnbudgetedSpend:
    category_id: Optional[int]
    name: str
    spent: float


@dataclass
class Suggestion:
    amount: float         # rounded up to the next ₹100
    months: int           # months of logged spending it is based on


@dataclass
class BudgetTotals:
    limit: float = 0.0
    spent: float = 0.0
    count: int = 0

    @property
    def remaining(self) -> float:
        return self.limit - self.spent


def typical_spend(history: list[PeriodSpend]) -> Optional[float]:
    """Average of the finished periods in which any spending was logged."""
    past = [p.spent for p in history if not p.current and p.logged]
    return sum(past) / len(past) if past else None


# --------------------------------------------------------------------------
# service
# --------------------------------------------------------------------------

class BudgetService:
    def __init__(
        self,
        repo: BudgetRepository,
        txn_repo: TransactionRepository,
        category_repo: CategoryRepository,
        fx_service=None,
        preferences: Optional[PreferencesService] = None,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        self.repo = repo
        self.txn_repo = txn_repo
        self.categories = category_repo
        self.fx = fx_service
        self.prefs = preferences if preferences is not None else PreferencesService(None)
        self._on_change = on_change

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change("budgets")

    # ------------------------------------------------------------ year start
    def year_start(self) -> int:
        try:
            month = int(self.prefs.get("budget_year_start", 1))
        except (TypeError, ValueError):
            return 1
        return month if month in YEAR_STARTS else 1

    def set_year_start(self, month: int) -> None:
        if month not in YEAR_STARTS:
            raise ValueError("A budget year starts in January or April")
        if month != self.year_start():
            self.prefs.set("budget_year_start", month)
            self._changed()

    def current_bounds(self, period: str, today: Optional[date] = None) -> tuple[date, date]:
        return period_bounds(period, today or date.today(), self.year_start())

    # ------------------------------------------------------------------ CRUD
    def list_all(self) -> list[Budget]:
        return [Budget.from_row(r) for r in self.repo.list_with_categories()]

    def get(self, budget_id: int) -> Optional[Budget]:
        return self.repo.get_by_id(budget_id)

    def for_category(self, category_id: int) -> list[Budget]:
        return self.repo.for_category(category_id)

    def _validate(self, category_id: Optional[int], period: str, amount) -> None:
        if period not in PERIODS:
            raise ValueError("Choose a monthly or a yearly limit")
        if amount is None or float(amount) <= 0:
            raise ValueError("The limit must be greater than zero")
        row = self.categories.get(category_id) if category_id is not None else None
        if row is None:
            raise ValueError("Choose a spending category")
        if row["kind"] != "expense":
            raise ValueError("Limits apply to spending (expense) categories only")

    def set_limit(self, category_id: int, period: str, amount: float,
                  notes: Optional[str] = None) -> int:
        """Set the category's limit for ``period``, replacing any existing one."""
        self._validate(category_id, period, amount)
        existing = self.repo.find(category_id, period)
        if existing is not None:
            existing.amount = round(float(amount), 2)
            existing.notes = notes or None
            existing.updated_at = _now()
            self.repo.update(existing)
            self._changed()
            return existing.id
        new_id = self.repo.insert(Budget(
            category_id=category_id, period=period,
            amount=round(float(amount), 2), notes=notes or None))
        self._changed()
        return new_id

    def update(self, budget: Budget) -> None:
        """Save an edited budget (category, period, limit or note)."""
        if budget.id is None:
            raise ValueError("Cannot update a budget without an id")
        current = self.repo.get_by_id(budget.id)
        if current is None:
            raise ValueError("That budget no longer exists")
        self._validate(budget.category_id, budget.period, budget.amount)
        clash = self.repo.find(budget.category_id, budget.period)
        if clash is not None and clash.id != budget.id:
            name = self.categories.get(budget.category_id)["name"]
            raise ValueError(f"{name} already has a {budget.period} limit - edit that one instead.")
        current.category_id = budget.category_id
        current.period = budget.period
        current.amount = round(float(budget.amount), 2)
        current.notes = budget.notes or None
        current.updated_at = _now()
        self.repo.update(current)
        self._changed()

    def delete(self, budget_id: int) -> None:
        self.repo.delete(budget_id)
        self._changed()

    # -------------------------------------------------------------- spending
    def _rupees(self, amount: float, currency: Optional[str]) -> Optional[float]:
        code = (currency or "INR").upper()
        if code == "INR":
            return amount
        return self.fx.convert(amount, code) if self.fx is not None else None

    def _month_totals(self, start: date, end: date, category_id: Optional[int] = None,
                      exclude_txn_id: Optional[int] = None):
        """Spending in [start, end] keyed by (category_id, 'YYYY-MM'):
        rupees, amounts without an exchange rate, and the months with any entry."""
        spent: dict[tuple, float] = {}
        unconverted: dict[tuple, dict[str, float]] = {}
        months: set[str] = set()
        rows = self.txn_repo.expense_totals(
            start.isoformat(), (end + timedelta(days=1)).isoformat(), category_id, exclude_txn_id)
        for r in rows:
            key = (r["category_id"], r["ym"])
            total = float(r["total"] or 0.0)
            if r["ym"]:
                months.add(r["ym"])
            inr = self._rupees(total, r["currency"])
            if inr is None:
                bucket = unconverted.setdefault(key, {})
                bucket[r["currency"]] = bucket.get(r["currency"], 0.0) + total
            else:
                spent[key] = spent.get(key, 0.0) + inr
        return spent, unconverted, months

    def _category_totals(self, start: date, end: date, category_id: Optional[int] = None,
                         exclude_txn_id: Optional[int] = None):
        spent, unconverted, _months = self._month_totals(start, end, category_id, exclude_txn_id)
        by_cat: dict[Optional[int], float] = {}
        unconv_by_cat: dict[Optional[int], dict[str, float]] = {}
        for (cid, _ym), v in spent.items():
            by_cat[cid] = by_cat.get(cid, 0.0) + v
        for (cid, _ym), bucket in unconverted.items():
            target = unconv_by_cat.setdefault(cid, {})
            for ccy, v in bucket.items():
                target[ccy] = target.get(ccy, 0.0) + v
        return by_cat, unconv_by_cat

    # ---------------------------------------------------------------- status
    def statuses(self, today: Optional[date] = None) -> list[BudgetStatus]:
        """Every budget in its current period - monthly first, then by category."""
        today = today or date.today()
        year_start = self.year_start()
        totals: dict[tuple[date, date], tuple] = {}
        out: list[BudgetStatus] = []
        for row in self.repo.list_with_categories():
            b = Budget.from_row(row)
            if b.period not in PERIODS:
                log.warning(f"Budget {b.id} has an unknown period {b.period!r}; ignored")
                continue
            bounds = period_bounds(b.period, today, year_start)
            if bounds not in totals:
                totals[bounds] = self._category_totals(*bounds)
            spent, unconverted = totals[bounds]
            out.append(BudgetStatus(
                b, row["category_name"], bounds[0], bounds[1],
                spent.get(b.category_id, 0.0), today,
                dict(unconverted.get(b.category_id, {}))))
        return out

    def status(self, budget_id: int, today: Optional[date] = None) -> Optional[BudgetStatus]:
        return next((s for s in self.statuses(today) if s.budget.id == budget_id), None)

    def alerts(self, today: Optional[date] = None) -> list[BudgetStatus]:
        """Budgets over or near their limit this period, worst first."""
        flagged = [s for s in self.statuses(today) if s.state != STATE_OK]
        return sorted(flagged, key=lambda s: (s.state != STATE_OVER, -s.pct))

    @staticmethod
    def totals(statuses: list[BudgetStatus], period: str) -> BudgetTotals:
        t = BudgetTotals()
        for s in statuses:
            if s.period == period:
                t.limit += s.limit
                t.spent += s.spent
                t.count += 1
        return t

    def history(self, budget_id: int, periods: int = 6,
                today: Optional[date] = None) -> list[PeriodSpend]:
        """This budget's category over the last ``periods`` periods, oldest
        first, ending with the current one - each against today's limit."""
        today = today or date.today()
        b = self.repo.get_by_id(budget_id)
        if b is None or b.period not in PERIODS or periods < 1:
            return []
        year_start = self.year_start()
        cur_start, cur_end = period_bounds(b.period, today, year_start)
        step = 1 if b.period == MONTHLY else 12
        first = _month_start(cur_start.year, cur_start.month, -step * (periods - 1))
        spent, _unconverted, months = self._month_totals(first, cur_end)
        out: list[PeriodSpend] = []
        for i in range(periods):
            start, end = period_bounds(
                b.period, _month_start(first.year, first.month, step * i), year_start)
            lo, hi = start.isoformat()[:7], end.isoformat()[:7]
            total = sum(v for (cid, ym), v in spent.items()
                        if cid == b.category_id and ym and lo <= ym <= hi)
            logged = any(lo <= ym <= hi for ym in months)
            out.append(PeriodSpend(start, end, period_label(b.period, start, short=True),
                                   total, float(b.amount or 0.0), start == cur_start, logged))
        return out

    def impact(self, category_id: Optional[int], txn_date, amount: float,
               currency: Optional[str] = "INR", exclude_txn_id: Optional[int] = None,
               today: Optional[date] = None) -> list[BudgetImpact]:
        """How an expense of ``amount`` on ``txn_date`` would leave each limit
        on its category. ``exclude_txn_id``: the entry being edited, so it is
        not counted twice."""
        if category_id is None:
            return []
        budgets = [b for b in self.repo.for_category(category_id) if b.period in PERIODS]
        if not budgets:
            return []
        today = today or date.today()
        on = _as_date(txn_date) or today
        row = self.categories.get(category_id)
        name = row["name"] if row else ""
        added = self._rupees(float(amount), currency) if amount else 0.0
        out: list[BudgetImpact] = []
        for b in sorted(budgets, key=lambda x: PERIODS.index(x.period)):
            start, end = period_bounds(b.period, on, self.year_start())
            spent, unconverted = self._category_totals(start, end, category_id, exclude_txn_id)
            status = BudgetStatus(b, name, start, end, spent.get(category_id, 0.0), today,
                                  dict(unconverted.get(category_id, {})))
            out.append(BudgetImpact(status, added))
        return out

    def unbudgeted(self, today: Optional[date] = None) -> list[UnbudgetedSpend]:
        """This month's spending in categories with no limit at all (including
        uncategorised spending), largest first."""
        start, end = period_bounds(MONTHLY, today or date.today())
        spent, _unconverted = self._category_totals(start, end)
        budgeted = {b.category_id for b in self.list_all()}
        names = self.categories.name_map()
        out = [UnbudgetedSpend(cid, names.get(cid, "Uncategorised") if cid is not None
                               else "Uncategorised", v)
               for cid, v in spent.items() if cid not in budgeted and v > _CENT]
        return sorted(out, key=lambda u: -u.spent)

    def suggestion(self, category_id: int, period: str,
                   today: Optional[date] = None) -> Optional[Suggestion]:
        """A starting limit from recent spending: the average month over the
        last three full months (or a year's worth of the average month over the
        last twelve), counting only months in which anything was logged."""
        today = today or date.today()
        n = 3 if period == MONTHLY else 12
        start = _month_start(today.year, today.month, -n)
        end = date(today.year, today.month, 1) - timedelta(days=1)
        spent, _unconverted, months = self._month_totals(start, end)
        if not months:
            return None
        total = sum(v for (cid, _ym), v in spent.items() if cid == category_id)
        if total <= _CENT:
            return None
        per_month = total / len(months)
        return Suggestion(_round_up(per_month if period == MONTHLY else per_month * 12),
                          len(months))
