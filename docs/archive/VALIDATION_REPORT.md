# Personal Finance Manager — Validation Report

> **⚠️ SUPERSEDED (2026-07-03):** This report is stale. See **`STATUS.md`** for
> the current, code-verified state of the project. Kept for historical context only.

**Goal of this review:** confirm the app is fit for *complete personal financial
planning over a 25–30 year horizon*, with well-linked data between entities,
consistent formatting, and reliable long-term storage. Findings below are tagged
**[Fixed]** (implemented in this pass), **[Partial]** (foundation implemented,
larger work recommended), or **[Recommended]** (not changed; proposed).

---

## Executive summary

The architecture is sound: a clean models → repositories → services → UI stack,
SQLite at runtime with human-readable JSON as the source of truth, additive
schema migrations, and consistent Indian-currency formatting. It already covers
accounts, transactions, income (with monthly actuals), investments, liabilities,
goals, projections, and net worth.

The most important gaps for a 25–30 year tool were **data durability** (data was
only saved on a clean quit, and the net-worth history table was never written)
and **cross-entity links** (liabilities, holdings, and income transactions were
not tied to accounts/sources). These have been addressed. Remaining items are
multi-currency aggregation, a versioned migration framework, and a few
planning-scope enhancements, detailed below.

---

## 1. Data linking & referential integrity

| Area | Finding | Status |
|------|---------|--------|
| Income → account | Each income source can be deposited into an account; monthly actuals post to the ledger. | [Fixed — earlier] |
| Liabilities → account | `liabilities` had no account link. Added `account_id` (schema + migration + model + dialog "Paid from account" + detail "Paid From"). | **[Fixed]** |
| Holdings → account | `holdings.linked_account_id` existed in the schema/model but was never exposed in the UI. Added a "Linked Account" picker to the holding dialog and a "Linked Account" row in the investment detail. | **[Fixed]** |
| Income transactions → source | A transaction's `income_source_id` could not be set from the Transactions UI. Added an "Income source" picker (enabled only for income transactions) wired through the view. | **[Fixed]** |
| Goals ↔ holdings | Goal dialog supports "Funded by Holdings"; `GoalService` syncs `current_amount` from linked holdings via `goal_holdings`. | **[Fixed]** |
| Debt double-counting | `accounts` carries descriptive `loan_*`/`cc_*` fields **and** there is a separate `liabilities` table. Saving an account with loan fields now shows an in-app reminder to use the Liabilities tab for debt totals. | **[Partial]** — convention documented + UI nudge; no hard block yet. |
| UI layering | Views imported `db` / repositories directly. All 8 views now receive `AppContext` and call services only. | **[Fixed]** |
| Regression tests | Minimal test coverage. `run_tests.bat` runs 23 tests: calculators, services, repositories, E2E persist/reload, UI smoke. | **[Fixed]** |

Foreign keys use sensible `ON DELETE` behavior (`CASCADE` for owned rows,
`SET NULL` for links), so deletes won't orphan or corrupt data.

---

## 2. Long-term storage & durability (25–30 years)

| Area | Finding | Status |
|------|---------|--------|
| Autosave | Data was persisted **only** on a clean quit (`aboutToQuit`); `AUTOSAVE_INTERVAL_SEC` was defined but unused. A crash/force-quit lost the whole session. Added a `QTimer` autosave that writes the store every interval (backup-free for speed). | **[Fixed]** |
| Net-worth history | `NetWorthService.take_snapshot()` existed but was **never called**, so `net_worth_snapshots` was always empty — a 30-year trend chart would have no data. Snapshots are now recorded on autosave and on shutdown (idempotent per day via `INSERT OR REPLACE` on the date). | **[Fixed]** |
| Backups | Only the last 10 backups were retained. Raised to 30 and made the pruning directory-safe. Each backup is a full store snapshot, and the live store always holds complete history, so this is rollback depth, not data retention. | **[Fixed]** |
| Date handling | Dates are stored as ISO `YYYY-MM-DD` text and timestamps via SQLite `CURRENT_TIMESTAMP` — **no Unix-epoch fields, so no 2038 problem.** Safe for a 30-year horizon. | OK |
| Volume at 30 years | Monthly rows (income entries, net-worth snapshots) total a few hundred per series; transactions are the only high-volume table and remain well within SQLite/JSON limits. | OK |
| JSON full-rewrite | On each save the entire store is rewritten. Fine at expected volumes; if transaction counts ever reach the high tens of thousands, consider switching the canonical store to SQLite-only with periodic JSON export. | [Recommended — future] |

---

## 3. Consistent formatting

| Area | Finding | Status |
|------|---------|--------|
| Entity views | Accounts, Income, Investments, Liabilities, and Goals now all use the same dark, warm-tan **tile** layout with a right-hand detail pane. | [Fixed — this & prior passes] |
| Tables that remain | Transactions and Projections still render as tables, and the Dashboard uses KPI cards. This is appropriate — ledgers and projections read better as tables — but it's a deliberate inconsistency to be aware of. | OK / by design |
| Currency display | Money was always formatted with `₹` regardless of an account's `currency`. Added a currency-aware `fmt_money(amount, currency, compact)` and switched the account tile to use it, so USD/EUR/etc. accounts display with the correct symbol and grouping. | **[Fixed]** |

---

## 4. Multi-currency

| Area | Finding | Status |
|------|---------|--------|
| Per-account display | Now currency-aware (see §3). | **[Fixed]** |
| Cross-currency aggregation | Net worth, total balances, portfolio value, and total outstanding use plain SQL `SUM(...)` with **no FX conversion** — a USD balance is added rupee-for-rupee to INR. | **[Partial / Recommended]** — until an FX layer exists, keep all accounts in a single base currency (INR). To support mixed currencies, add an `fx_rates` reference (base = INR), convert non-base amounts in the aggregation paths (`account_repo.total_balance`, `holding_repo.total_current_value`, `other_repos.total_outstanding`), and store each amount's currency. This is a deliberate, well-scoped follow-up because it touches every aggregation and needs live/maintained rates. |

---

## 5. Scope for long-term financial planning

Coverage is strong: net worth, accounts, a universal transaction ledger,
income with monthly actuals and account linkage, a polymorphic holdings model
(SIP, FD, stocks, gold, insurance, bonds, NPS, …), liabilities with EMI math,
goals with required-SIP and inflation/return assumptions, and a projections tab.
Calculators (`fv_of_sip`, `required_monthly_sip`, `emi`, `xirr`) are correct.

Recommended enhancements for true long-horizon planning:

- **Goal funding from holdings** (see §1) so progress is real, not hand-entered.
- **Retirement/FIRE projection** built on the existing SIP/FV calculators and the
  net-worth trend now being recorded.
- **Recurring transactions** (salary, SIPs, EMIs, premiums) auto-posted monthly,
  reusing the scheduled-income pattern already built for income.
- **Inflation-adjusted ("real") views** on long-range projections.
- **XIRR per holding/portfolio** surfaced in the UI (the calculator exists).

---

## 6. Schema migration robustness

`db/migrate.py` performs idempotent additive `ALTER TABLE ADD COLUMN` only; it
cannot rename, drop, retype, or retrofit constraints, and there is no schema
version table. This has been sufficient so far (account detail columns, income
`deposit_account_id`, liability `account_id`) but is fragile for a schema that
will evolve over decades.

**[Recommended]** Introduce a lightweight versioned migration runner: a
`schema_version` table plus an ordered list of migration callables, each bumping
the version. Keep the current additive helper as migration #1. This enables safe
structural changes (renames, backfills) in future years without manual surgery.

---

## 7. Input validation & integrity

`utils/validators.py` provides `is_positive_number`, `is_non_negative`,
`is_valid_date`, `is_non_empty_str`, but dialogs do ad-hoc inline checks instead
and don't import it. Numeric inputs are constrained by spin boxes and dates by
date pickers, so the risk is low, but validation is inconsistent.

**[Recommended]** Route dialog validation through `validators.py` for uniform
messages and add light sanity checks (e.g., remaining-months ≤ tenure, current
value not wildly above invested without confirmation).

---

## Changes implemented in this pass

1. **Autosave** — periodic `QTimer` save (`main.py`) so a crash loses at most one interval.
2. **Net-worth snapshots** recorded on autosave and shutdown (`main.py` + existing `NetWorthService.take_snapshot`).
3. **Backups** retention raised to 30 with safe pruning (`data_persister.py`).
4. **Liabilities → account** link: `account_id` added (schema, migration, model, dialog, view/detail).
5. **Holdings → account** link surfaced in the holding dialog and investment detail.
6. **Income transactions → income source** picker added to the transaction dialog and wired through the Transactions view.
7. **Currency-aware formatting** (`fmt_money`) and applied to the account tile.

## Recommended follow-ups (not yet implemented)

- Goal ↔ holdings linking (populate `goal_holdings`; derive goal progress).
- Cross-currency aggregation via an FX layer (base = INR).
- Versioned migration framework (`schema_version` + ordered migrations).
- Centralized input validation via `validators.py`.
- Retirement projection, recurring transactions, inflation-adjusted views, UI XIRR.
