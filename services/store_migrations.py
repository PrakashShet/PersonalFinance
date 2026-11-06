"""Versioned migrations for the JSON store - the source of truth.

SQLite is rebuilt from the store on every launch, so schema changes never need
an SQLite migration. Changes to the *meaning or shape* of stored records do,
and they belong here: each migration is a function over the in-memory tables
(``{filename: [records]}``), run in order, after a ``pre-migration`` backup.

The store's version lives in ``data/store/_meta.json``. A store with data but
no meta file is version 1 (everything written before 1.0).

A store *newer* than this app understands is refused rather than loaded: an
older app could silently drop fields it doesn't know.

Adding a migration
    1. bump ``STORE_VERSION``
    2. write ``_vN_<what>(tables, today) -> list[str]`` (notes for the log)
    3. register it in ``MIGRATIONS``
    4. add a test in tests/test_services/test_store_migrations.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Callable

from services import ledger
from services.data_loader import STORE_LOAD_ORDER, StoreLoadError, StoreTables
from utils.json_handler import write_text_atomic

STORE_VERSION = 2
META_FILE = "_meta.json"

_ABOUT = (
    "Personal Finance Manager data store. Each *.json file in this folder is one "
    "table: a list of records (objects). Amounts are plain numbers in the account's "
    "currency (INR unless stated); dates are ISO YYYY-MM-DD. Account balances equal "
    "the sum of their transactions (see services/ledger.py)."
)


class StoreVersionError(Exception):
    """The store was written by a newer version of the app."""

    def __init__(self, found: int, supported: int) -> None:
        self.found = found
        self.supported = supported
        super().__init__(
            f"The data store is version {found}, but this app only understands up to "
            f"version {supported}. Please use the newer version of the app."
        )


# --------------------------------------------------------------------------
# meta file
# --------------------------------------------------------------------------

def read_meta(store_dir: Path) -> dict:
    store_dir = Path(store_dir)
    path = store_dir / META_FILE
    if not path.exists():
        has_data = any((store_dir / f).exists() for f, _ in STORE_LOAD_ORDER)
        return {"store_version": 1 if has_data else STORE_VERSION, "_missing": True}
    try:
        meta = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise StoreLoadError(path, f"could not be read ({e}).") from e
    if not isinstance(meta, dict) or not isinstance(meta.get("store_version"), int):
        raise StoreLoadError(path, "does not contain a valid store_version.")
    return meta


def write_meta(store_dir: Path, version: int, app_version: str = "") -> None:
    meta = {
        "store_version": version,
        "written_by": f"Personal Finance Manager {app_version}".strip(),
        "about": _ABOUT,
    }
    write_text_atomic(
        Path(store_dir) / META_FILE,
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
    )


# --------------------------------------------------------------------------
# migrations
# --------------------------------------------------------------------------

def _v2_ledger_invariant(tables: StoreTables, today: date) -> list[str]:
    """v2: every active account's balance is explained by its transactions.

    1. Opening balances that were posted as ``income`` (tag ``opening-balance``)
       become ``adjustment``s - they are not income, and counted as income they
       inflated that month's income and savings figures.
    2. Accounts with an opening balance but no opening entry get one, dated at
       the account's creation (or its earliest transaction, if earlier).
    3. Any remaining difference between the stored balance and the ledger -
       balances edited directly, entries imported without a balance effect - is
       recorded as a dated reconciliation ``adjustment``.

    Stored balances are never changed, so net worth is identical before and
    after; the ledger is completed to explain it.
    """
    notes: list[str] = []
    accounts = tables.get("accounts.json") or []
    txns = tables.get("transactions.json")
    if txns is None:
        txns = []
        tables["transactions.json"] = txns

    converted = 0
    for t in txns:
        if t.get("txn_type") == "income" and ledger.has_tag(t.get("tags"), ledger.OPENING_TAG):
            t["txn_type"] = ledger.ADJUSTMENT
            t["category_id"] = None
            converted += 1
    if converted:
        notes.append(f"Re-classified {converted} opening-balance entr(y/ies) from income to adjustment")

    implied = ledger.balances(txns)
    has_opening = {
        t.get("account_id") for t in txns if ledger.has_tag(t.get("tags"), ledger.OPENING_TAG)
    }
    next_id = max((int(t.get("id") or 0) for t in txns), default=0) + 1
    stamp = f"{today.isoformat()} 00:00:00"

    def add(account_id: int, amount: float, when: str, description: str, tag: str) -> None:
        nonlocal next_id
        txns.append({
            "id": next_id,
            "txn_date": when,
            "txn_type": ledger.ADJUSTMENT,
            "amount": round(amount, 2),
            "account_id": account_id,
            "counter_account_id": None,
            "category_id": None,
            "holding_id": None,
            "income_source_id": None,
            "description": description,
            "reference_no": None,
            "tags": tag,
            "created_at": stamp,
        })
        next_id += 1

    for a in accounts:
        if not a.get("is_active", 1):
            continue                     # archived accounts are frozen history
        aid = a.get("id")
        if aid is None:
            continue
        name = a.get("name") or f"account {aid}"
        balance = implied.get(aid, 0.0)

        opening = float(a.get("opening_balance") or 0.0)
        if aid not in has_opening and abs(opening) >= ledger.CENT:
            when = str(a.get("created_at") or today.isoformat())[:10]
            dates = [
                str(t.get("txn_date"))[:10] for t in txns
                if aid in (t.get("account_id"), t.get("counter_account_id")) and t.get("txn_date")
            ]
            if dates and min(dates) < when:
                when = min(dates)
            add(aid, opening, when, "Opening balance", ledger.OPENING_TAG)
            balance += opening
            notes.append(f"{name}: added opening balance entry {opening:+,.2f}")

        diff = round(float(a.get("current_balance") or 0.0) - balance, 2)
        if abs(diff) >= 0.01:
            add(
                aid, diff, today.isoformat(),
                "Balance reconciliation (1.0 upgrade)",
                ledger.RECONCILE_TAG,
            )
            notes.append(f"{name}: recorded reconciliation adjustment {diff:+,.2f}")
    return notes


MIGRATIONS: list[tuple[int, Callable[[StoreTables, date], list[str]]]] = [
    (2, _v2_ledger_invariant),
]


def migrate(tables: StoreTables, from_version: int, today: date | None = None) -> list[str]:
    """Bring ``tables`` (mutated in place) up to ``STORE_VERSION``."""
    if from_version > STORE_VERSION:
        raise StoreVersionError(from_version, STORE_VERSION)
    today = today or date.today()
    notes: list[str] = []
    for target, fn in MIGRATIONS:
        if from_version < target:
            notes.extend(fn(tables, today))
    return notes
