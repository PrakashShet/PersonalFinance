---
name: data-hygiene
description: Audit the Personal Finance Manager's data/store/*.json files for balances the ledger doesn't explain, junk records, orphaned foreign keys, silent zero valuations, missing exchange rates and budgets the app can't use. Use when net worth or dashboard numbers look wrong, before trusting a report, after bulk edits or imports, or as a periodic check on the real financial data.
---

# Auditing the store

`data/store/*.json` is the source of truth. SQLite is rebuilt from it in memory
at every launch, so every data problem is visible in those files, and every fix
belongs there, preferably made through the app.

## Run the audit

```bash
python docs/skills/data-hygiene/check_store.py
python docs/skills/data-hygiene/check_store.py --store <path>     # a backup, a copy, the demo
```

The audit is read-only: it never writes, and it is safe to run while the app is
open. Exit codes: `0` clean, `1` findings, `2` store unreadable. To compare
against a known-good day, point `--store` at a backup in
`data/user/backups/<timestamp>/`.

It prints the store format version and row counts, then recomputes net worth the
way `NetWorthService.compute` does (compare the figure with the Dashboard), and
then lists its findings.

## What it checks, and why each matters

| Check | Why it matters |
|-------|----------------|
| **Ledger vs balance** (format v2+) | Every active account's balance must equal the sum of its transactions. A difference means the JSON was edited by hand or a write bypassed the ledger, and later edits to old entries will produce wrong balances. Fix in the app: Accounts → Reconcile |
| **Placeholder names** (`test`, `qwe`, `asdf`, `dummy`…) | Throwaway records left active inflate every total and get baked into `net_worth_snapshots` |
| **Orphaned foreign keys** | The JSON has no foreign-key enforcement, but SQLite enforces it at load, so a dangling id **stops the app from starting** (it fails closed and overwrites nothing) |
| **Zero-valued holdings** | A holding with money invested but a `current_value` of 0 or null adds nothing to net worth. Term insurance is excluded, because it is protection, not an investment |
| **Inactive rows with balances** | Totals only count `is_active = 1`, so money in an archived account is left out |
| **Untracked loans** | A loan described on an account counts in net worth only once it is a liability linked by `liabilities.account_id` (Accounts → Track in Liabilities) |
| **Missing exchange rates** | A non-INR balance without a row in `fx_rates.json` is left out of net worth and budgets (Settings → Exchange rates) |
| **Budgets** | A duplicate (category, period) pair or a budget with no category **stops the app from starting**. An unknown period, a limit of 0 or less, or a budget on an income category is ignored or never fills up |
| **Non-ISO dates** | Everything downstream assumes `YYYY-MM-DD` |

## Fixing findings

Most findings have an in-app fix: Reconcile, Archive, Track in Liabilities, an
exchange rate, or editing or deleting a budget. For anything else:

1. **Close the app.** It saves within a second of every change, and again when
   it quits.
2. **Back up.** Copy `data/store/`, or use Settings → Back up now before closing.
3. **Edit the JSON file.** Keep it a list of objects, keep dates in ISO format,
   and keep every `id` unique.
4. **Relaunch.** If the file no longer parses, or a record points at something
   missing, the app refuses to start and names the file. Nothing is
   overwritten; fix it and try again.
5. **Re-run the audit.** It catches orphans you have just created.

**Historical snapshots don't correct themselves.** Each `net_worth_snapshots` row
was computed from that day's data, so removing a bogus account today does not fix
past rows. Correct them deliberately, with a small script that refuses to run if
the data isn't exactly what it expects, and take a backup first.

Before deleting a row, check that nothing references it:
`transactions.account_id` / `counter_account_id` / `category_id`,
`holdings.linked_account_id`, `liabilities.account_id`,
`income_sources.deposit_account_id`, `goal_holdings.*`,
`holding_valuations.holding_id`, `budgets.category_id`.

## Extending the script

- `STORE_FILES` must stay in sync with `STORE_LOAD_ORDER` in `services/data_loader.py`.
- `LINKS` maps each child file to `[(field, parent file)]`. Add an entry when a new
  foreign key appears.
- `_effects` mirrors `services/ledger.effects`. Change them together.
- The script uses plain Python and no project imports, on purpose: it must still
  run when the app itself can't.
