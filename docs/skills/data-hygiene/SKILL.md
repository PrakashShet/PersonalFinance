---
name: data-hygiene
description: Audit the Personal Finance Manager's data/store/*.json files for junk records, orphaned foreign keys, silent zero valuations, and mixed currencies. Use when net worth or dashboard numbers look wrong, before trusting a report, after bulk edits or imports, or as a periodic check on the real financial data.
---

# Auditing the store

`data/store/*.json` is the source of truth — `data/app.db` is rebuilt from it on every
boot. So every data problem is visible in those files, and every fix belongs there.

## Run the audit

```bash
python docs/skills/data-hygiene/check_store.py
```

Read-only: never writes, never touches `app.db`, safe with the app running.
Exit `0` clean, `1` findings, `2` store unreadable. Use `--store <path>` to point at a
backup under `data/user/backups/<timestamp>/` and compare against a known-good day.

It prints row counts, recomputes net worth the same way `NetWorthService.compute` does
(so you can diff it against the Dashboard), then lists findings by severity.

## What it checks, and why each matters

| Check | Why it matters |
|-------|----------------|
| **Placeholder names** (`test`, `qwe`, `asdf`, `dummy`…) | Throwaway records left `is_active=1` silently inflate every total and get baked into `net_worth_snapshots` permanently |
| **Orphaned FKs** | The JSON store has no FK enforcement — only SQLite does, at load. A dangling `account_id` either fails the boot load or silently detaches the row |
| **Zero-valued holdings** | `total_current_value` sums `current_value`; a holding with money invested but `current_value` of 0/null contributes nothing and vanishes from net worth. Term insurance is excluded — it legitimately has no surrender value |
| **Inactive rows with balances** | Aggregations filter on `is_active = 1`, so money in a deactivated account disappears from totals without warning |
| **Duplicate debt** | A loan can exist as `accounts.loan_*` fields *and* a `liabilities` row. Only a soft UI nudge prevents this; nothing reconciles it |
| **Mixed currencies** | Aggregations are plain `SUM()` with no FX conversion — a USD balance is added rupee-for-rupee. `has_mixed_currencies()` exists but does not adjust totals |
| **Non-ISO dates** | Everything downstream assumes `YYYY-MM-DD`; `date.fromisoformat` raises or silently misparses otherwise |

## Fixing findings

**Close the app first.** It autosaves every 60 seconds and dumps the whole store on
quit, so a running app will overwrite your edits.

1. Back up: copy `data/store/` somewhere, or grab the newest `data/user/backups/<ts>/`
2. Edit the offending JSON file directly
3. Delete `data/app.db` (optional but clean — it is rebuilt from JSON on boot)
4. Relaunch and confirm the Dashboard matches the script's recomputed net worth

**Prefer deletion over deactivation for junk.** Setting `is_active=0` keeps the row in
history and in every existing snapshot. If a record was never real, remove it.

**Historical snapshots do not self-correct.** `net_worth_snapshots.json` holds one row
per day the app ran, each computed from that day's data. Deleting a bogus account today
does **not** fix yesterday's snapshot — the trend chart stays wrong. Either accept the
discontinuity or hand-edit the affected snapshot rows.

Before deleting a row, check nothing references it — `transactions.account_id`,
`holdings.linked_account_id`, `liabilities.account_id`, `income_sources.deposit_account_id`,
`goal_holdings.{goal_id,holding_id}`, `holding_valuations.holding_id`. Re-run the script
after editing; it will catch orphans you just created.

## Known outstanding finding

The live store currently contains an account named **`qwe`** (id=7) holding
₹50,00,000 with `is_active=1`. It is placeholder data, it is in every net-worth figure
the app reports, and it has already contaminated the recorded snapshots. Removing it
moves net worth from roughly +₹23L to about −₹27L, which is the real number.

## Extending the script

`LINKS` maps child file → `[(field, parent file)]`; add an entry when a new FK appears.
`JUNK_NAME` is the placeholder-name regex. `STORE_FILES` must stay in sync with
`STORE_LOAD_ORDER` in `services/data_loader.py`.
