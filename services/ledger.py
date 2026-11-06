"""The ledger's balance rules - one definition, used everywhere.

Invariant (store format v2+): for every active account,

    current_balance == sum of effect(t) over every transaction t touching it

Balance effect by transaction type (on ``account_id`` unless noted):

    income, investment_sell   +amount
    expense, investment_buy   -amount
    transfer                  -amount on account_id, +amount on counter_account_id
    adjustment                +amount (signed: negative removes money)

``adjustment`` is not income or spending. It records an opening balance, a
balance the user corrected by hand, or a reconciliation, and is excluded from
every income / expense / savings figure.

Pure functions only (no DB, no Qt) so the store migration, the services and
the audit script all agree on the arithmetic.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

INFLOW = frozenset({"income", "investment_sell"})
OUTFLOW = frozenset({"expense", "investment_buy"})
TRANSFER = "transfer"
ADJUSTMENT = "adjustment"
ALL_TYPES = frozenset(INFLOW | OUTFLOW | {TRANSFER, ADJUSTMENT})

# Tags written on machine-generated adjustments.
OPENING_TAG = "opening-balance"
RECONCILE_TAG = "reconciliation"
ADJUST_TAG = "balance-adjustment"

CENT = 0.005  # differences below half a paisa are rounding noise


def _get(txn: Any, key: str) -> Any:
    if isinstance(txn, Mapping):
        return txn.get(key)
    return getattr(txn, key, None)


def effects(txn: Any) -> list[tuple[int, float]]:
    """``[(account_id, delta), ...]`` this transaction applies to balances."""
    t = _get(txn, "txn_type")
    amount = float(_get(txn, "amount") or 0.0)
    account = _get(txn, "account_id")
    if t in INFLOW or t == ADJUSTMENT:
        return [(account, amount)]
    if t in OUTFLOW:
        return [(account, -amount)]
    if t == TRANSFER:
        out = [(account, -amount)]
        counter = _get(txn, "counter_account_id")
        if counter:
            out.append((counter, amount))
        return out
    return []


def balances(txns: Iterable[Any]) -> dict[int, float]:
    """Ledger-implied balance per account id."""
    totals: dict[int, float] = defaultdict(float)
    for t in txns:
        for account_id, delta in effects(t):
            if account_id is not None:
                totals[account_id] += delta
    return dict(totals)


def signed_amount(txn_type: str, amount: float) -> float:
    """Amount signed by its effect on the primary account."""
    if txn_type in OUTFLOW or txn_type == TRANSFER:
        return -abs(amount)
    if txn_type == ADJUSTMENT:
        return amount
    return abs(amount)


def has_tag(tags: str | None, tag: str) -> bool:
    return tag in [t.strip() for t in (tags or "").split(",") if t.strip()]
