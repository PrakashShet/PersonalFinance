#!/usr/bin/env python3
"""Audit data/store/*.json for junk, orphans, and silent zeros.

Read-only: never writes, never touches app.db. Safe to run any time.

Usage:
    python docs/skills/data-hygiene/check_store.py
    python docs/skills/data-hygiene/check_store.py --store path/to/store

Exit codes: 0 = clean, 1 = findings, 2 = could not read the store.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Names that almost always mean a throwaway record rather than real data.
JUNK_NAME = re.compile(
    r"^(test\d*|asdf?|qwe\w*|zxc\w*|foo|bar|baz|abc|xyz|aaa+|xxx+|1234\d*|delete\s?me|dummy|sample|temp)$",
    re.IGNORECASE,
)

STORE_FILES = [
    "accounts.json", "categories.json", "income_sources.json", "holdings.json",
    "liabilities.json", "goals.json", "goal_holdings.json", "transactions.json",
    "income_entries.json", "holding_valuations.json", "net_worth_snapshots.json",
    "reminders.json",
]

# child file -> [(child field, parent file)]
LINKS = {
    "transactions.json": [("account_id", "accounts.json"),
                          ("category_id", "categories.json"),
                          ("income_source_id", "income_sources.json")],
    "holdings.json": [("linked_account_id", "accounts.json")],
    "liabilities.json": [("account_id", "accounts.json")],
    "income_sources.json": [("deposit_account_id", "accounts.json")],
    "income_entries.json": [("income_source_id", "income_sources.json")],
    "goal_holdings.json": [("goal_id", "goals.json"),
                           ("holding_id", "holdings.json")],
    "holding_valuations.json": [("holding_id", "holdings.json")],
}

findings: list[tuple[str, str]] = []


def flag(severity: str, msg: str) -> None:
    findings.append((severity, msg))


def load(store: Path, name: str):
    path = store / name
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        flag("ERROR", f"{name} is not valid JSON: {e}")
        return None
    if not isinstance(data, list):
        flag("ERROR", f"{name} should hold a JSON list, found {type(data).__name__}")
        return None
    return data


def label(row: dict) -> str:
    return str(row.get("name") or row.get("description") or f"id={row.get('id')}")


def money(x) -> str:
    try:
        return f"{float(x):,.2f}"
    except (TypeError, ValueError):
        return str(x)


def check_junk(tables: dict) -> None:
    for fname, rows in tables.items():
        for r in rows or []:
            name = str(r.get("name") or "").strip()
            if name and JUNK_NAME.match(name):
                active = r.get("is_active", 1)
                bal = r.get("current_balance") or r.get("current_value") or r.get("outstanding") or 0
                sev = "HIGH" if active and float(bal or 0) else "LOW"
                extra = f", carrying {money(bal)}" if bal else ""
                flag(sev, f"{fname}: placeholder-looking record '{name}' "
                          f"(id={r.get('id')}, is_active={active}{extra})")


def check_orphans(tables: dict) -> None:
    ids = {f: {r.get("id") for r in (rows or [])} for f, rows in tables.items()}
    for child, links in LINKS.items():
        for r in tables.get(child) or []:
            for field, parent in links:
                val = r.get(field)
                if val in (None, "", 0):
                    continue
                if parent in ids and val not in ids[parent]:
                    flag("HIGH", f"{child}: '{label(r)}' points at "
                                 f"{field}={val}, which does not exist in {parent}")


def check_zero_values(tables: dict) -> None:
    for r in tables.get("holdings.json") or []:
        if not r.get("is_active", 1):
            continue
        htype = str(r.get("holding_type") or "")
        invested = float(r.get("invested_amount") or 0)
        current = r.get("current_value")
        # Term insurance legitimately has no surrender value.
        if "term_insurance" in htype:
            continue
        if invested > 0 and (current is None or float(current) == 0):
            flag("MED", f"holdings.json: '{label(r)}' has invested "
                        f"{money(invested)} but current_value is "
                        f"{'null' if current is None else '0'} — it contributes "
                        f"nothing to net worth")


def check_inactive_with_balance(tables: dict) -> None:
    for r in tables.get("accounts.json") or []:
        if not r.get("is_active", 1) and float(r.get("current_balance") or 0):
            flag("MED", f"accounts.json: '{label(r)}' is inactive but still holds "
                        f"{money(r.get('current_balance'))} — excluded from totals")


def check_duplicate_debt(tables: dict) -> None:
    """The same loan can legitimately exist as an account AND a liability."""
    loans = [r for r in (tables.get("accounts.json") or [])
             if float(r.get("loan_outstanding") or 0) > 0
             or float(r.get("loan_principal") or 0) > 0
             or r.get("loan_type")]
    if loans and (tables.get("liabilities.json") or []):
        names = ", ".join(f"'{label(r)}'" for r in loans)
        flag("MED", f"accounts.json: {len(loans)} account(s) carry loan fields "
                    f"({names}) while liabilities.json also has rows — confirm the "
                    f"same debt isn't counted twice")
    for r in tables.get("accounts.json") or []:
        if float(r.get("cc_outstanding") or 0) > 0:
            flag("LOW", f"accounts.json: '{label(r)}' has cc_outstanding "
                        f"{money(r.get('cc_outstanding'))}; credit_card accounts are "
                        f"excluded from total_balance, so verify it's tracked in "
                        f"liabilities.json instead")


def check_currency(tables: dict) -> None:
    ccy = {(r.get("currency") or "INR") for r in (tables.get("accounts.json") or [])}
    if len(ccy) > 1:
        flag("HIGH", f"accounts.json: mixed currencies {sorted(ccy)} — aggregations "
                     f"use plain SUM() with no FX conversion, so net worth is wrong")


def check_dates(tables: dict) -> None:
    iso = re.compile(r"^\d{4}-\d{2}-\d{2}")
    for fname, rows in tables.items():
        for r in rows or []:
            for k, v in r.items():
                if k.endswith("_date") and v and not iso.match(str(v)):
                    flag("MED", f"{fname}: '{label(r)}' field {k}={v!r} is not "
                                f"ISO YYYY-MM-DD")


def net_worth(tables: dict) -> None:
    cash = sum(float(r.get("current_balance") or 0)
               for r in (tables.get("accounts.json") or [])
               if r.get("is_active", 1) and r.get("account_type") != "credit_card")
    inv = sum(float(r.get("current_value") or 0)
              for r in (tables.get("holdings.json") or []) if r.get("is_active", 1))
    liab = sum(float(r.get("outstanding") or 0)
               for r in (tables.get("liabilities.json") or []) if r.get("is_active", 1))
    print(f"  cash & bank      {money(cash):>18}")
    print(f"  investments      {money(inv):>18}")
    print(f"  liabilities     -{money(liab):>18}")
    print(f"  {'net worth':<16} {money(cash + inv - liab):>18}")
    print("  (mirrors NetWorthService.compute; compare against the Dashboard)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default=None, help="path to data/store")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[3]
    store = Path(args.store) if args.store else root / "data" / "store"
    if not store.is_dir():
        print(f"Store directory not found: {store}", file=sys.stderr)
        return 2

    print(f"Auditing {store}\n")
    tables = {}
    for name in STORE_FILES:
        rows = load(store, name)
        if rows is None and not (store / name).exists():
            flag("LOW", f"{name} is missing (loader will recreate it as [])")
        tables[name] = rows or []

    print("Row counts:")
    for name, rows in tables.items():
        print(f"  {name:<28} {len(rows):>5}")

    print("\nNet worth from store files:")
    net_worth(tables)

    check_junk(tables)
    check_orphans(tables)
    check_zero_values(tables)
    check_inactive_with_balance(tables)
    check_duplicate_debt(tables)
    check_currency(tables)
    check_dates(tables)

    print()
    if not findings:
        print("No issues found.")
        return 0

    order = {"ERROR": 0, "HIGH": 1, "MED": 2, "LOW": 3}
    findings.sort(key=lambda f: order.get(f[0], 9))
    print(f"{len(findings)} finding(s):\n")
    for sev, msg in findings:
        print(f"  [{sev:<5}] {msg}")
    print("\nNothing was modified. Fix by editing data/store/*.json while the app is "
          "CLOSED, then relaunch (app.db is rebuilt from these files).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
