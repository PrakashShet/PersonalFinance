"""How budgets are worded - shared by the Budgets page, the Dashboard and the
transaction dialog, so a limit reads the same everywhere."""
from __future__ import annotations

from typing import Optional

from services.budget_service import (
    MONTHLY,
    STATE_NEAR,
    STATE_OK,
    STATE_OVER,
    YEARLY,
    BudgetImpact,
    BudgetStatus,
)
from utils.formatters import fmt_inr

STATE_TONE = {STATE_OK: "", STATE_NEAR: "warning", STATE_OVER: "negative"}
STATE_BADGE = {STATE_NEAR: ("Near limit", "warning"), STATE_OVER: ("Over limit", "negative")}
PERIOD_NAMES = {MONTHLY: "Monthly", YEARLY: "Yearly"}
PERIOD_OPTIONS = [(MONTHLY, "Every month"), (YEARLY, "Every year")]
YEAR_START_OPTIONS = [("1", "January – December"), ("4", "April – March (financial year)")]


def money(amount: float) -> str:
    """Budgets are planned in whole rupees."""
    return fmt_inr(amount, decimals=0)


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def period_phrase(status: BudgetStatus) -> str:
    """'this month', 'this year', 'this financial year' or 'in October 2026'."""
    if not status.is_current:
        return f"in {status.label}"
    if status.period == MONTHLY:
        return "this month"
    return "this year" if status.start.month == 1 else "this financial year"


def left_text(status: BudgetStatus) -> str:
    if status.state == STATE_OVER:
        return f"{money(-status.remaining)} over"
    return f"{money(status.remaining)} left"


def allowance_text(status: BudgetStatus) -> str:
    """'About ₹120 a day for the 25 days left' - empty when nothing is left."""
    amount = status.allowance()
    if amount is None or not status.is_current:
        return ""
    if status.period == MONTHLY:
        return f"About {money(amount)} a day for the {_plural(status.days_left, 'day')} left"
    return f"About {money(amount)} a month for the {_plural(status.months_left, 'month')} left"


def alert_texts(status: BudgetStatus) -> tuple[str, str]:
    """Title and detail for a budget that needs attention."""
    when = period_phrase(status)
    if status.state == STATE_OVER:
        return (f"{status.category_name} is over budget",
                f"{money(status.spent)} spent of {money(status.limit)} {when}")
    return (f"{status.category_name} is near its limit",
            f"{money(status.remaining)} left of {money(status.limit)} {when}")


def impact_hint(impacts: list[BudgetImpact]) -> Optional[tuple[str, str]]:
    """The line under the category while an expense is being entered, and its
    tone: what is left now, or what would be left after this expense."""
    if not impacts:
        return None
    lines: list[str] = []
    states: list[str] = []
    for imp in impacts:
        st = imp.status
        name, limit, when = st.category_name, money(st.limit), period_phrase(st)
        if imp.added:                                   # an amount has been typed
            state = imp.state_after
            if state == STATE_OVER:
                line = f"{name} would be {money(-imp.remaining_after)} over its {limit} limit {when}."
            else:
                line = f"{name} would have {money(imp.remaining_after)} of {limit} left {when}."
        else:
            state = st.state
            if state == STATE_OVER:
                line = f"{name} is already {money(-st.remaining)} over its {limit} limit {when}."
            else:
                line = f"{name} has {money(st.remaining)} of {limit} left {when}."
            if imp.added is None:
                line += " This amount isn't counted: its currency has no exchange rate."
        lines.append(line)
        states.append(state)
    worst = STATE_OVER if STATE_OVER in states else (STATE_NEAR if STATE_NEAR in states else STATE_OK)
    return "\n".join(lines), STATE_TONE[worst]
