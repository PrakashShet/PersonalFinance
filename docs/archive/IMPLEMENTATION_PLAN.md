# Implementation Plan — Remaining Gaps (Phases 7+)

Continuation of `CLEANUP_PLAN.md` (Phases 1–6, done). See `STATUS.md` for the
audit this plan is based on. Each phase is independent and can be picked up
separately in Cursor — file paths and target signatures are given so the
diff stays small and additive.

---

## Phase 7 — Multi-currency / FX aggregation (Medium priority)

**Problem:** `account_repo.total_balance()`, `holding_repo.total_current_value()`,
`holding_repo.total_invested()`, `liability_repo.total_outstanding()` all use
plain `SUM()`. If any account/holding/liability has `currency != "INR"`, totals
are wrong (added at face value, not converted).

**Plan:**
1. `db/schema.sql`: add
   ```sql
   CREATE TABLE IF NOT EXISTS fx_rates (
     currency TEXT PRIMARY KEY,   -- e.g. 'USD', 'EUR'
     rate_to_base REAL NOT NULL,  -- 1 unit of currency = rate_to_base INR
     updated_at TEXT DEFAULT (datetime('now'))
   );
   ```
2. `repositories/`: new `FxRateRepository` (thin, `get_rate(currency) -> float`,
   `upsert(currency, rate)`, `list_all()`). Default INR = 1.0 (don't store, treat
   missing currency as 1.0 in the conversion helper).
3. `services/fx_service.py`: `FxService.to_base(amount, currency) -> float`
   (multiplies by rate, defaults to 1.0 for INR/unknown).
4. Update aggregation call sites to convert per-row instead of `SUM()` in SQL:
   - `AccountRepository.total_balance()` → fetch `(current_balance, currency)`
     pairs, convert in Python via `FxService`.
   - `HoldingRepository.total_current_value()` / `total_invested()` — holdings
     don't currently have a `currency` column; either add one (nullable,
     default INR) or document that holdings are INR-only for now (cheaper).
   - `LiabilityRepository.total_outstanding()` — same as accounts if liabilities
     ever get a `currency` column; otherwise leave as-is and note in README.
5. `NetWorthService.compute()` and dashboard KPIs call through `FxService`.
6. Add a small "Manage FX rates" entry point (could be a simple dialog or a row
   in Settings) so the user maintains rates manually — no live API calls
   (keeps the app offline-friendly per the README's data philosophy).
7. Tests: `tests/test_services/test_fx_service.py` (conversion math),
   extend `tests/test_repositories/test_account_repo.py` for a non-INR account
   total.

**Acceptance:** an account with `currency='USD'` and `current_balance=100`
contributes `100 * fx_rate('USD')` (not `100`) to `total_balance()` /
dashboard net worth.

---

## Phase 8 — `stock_master` table (Low priority)

**Problem:** `services/data_loader.py` lines ~58-66 guard on
`_table_exists("stock_master")`, which is always `False` because `schema.sql`
never declares the table. `data/seed/stock_master.csv` is loaded nowhere.

**Plan:**
1. `db/schema.sql`: add
   ```sql
   CREATE TABLE IF NOT EXISTS stock_master (
     symbol TEXT PRIMARY KEY,
     name TEXT,
     market_cap TEXT,   -- 'sme' | 'small' | 'mid' | 'large'
     sector TEXT
   );
   ```
2. Confirm `data/seed/stock_master.csv` columns match (`symbol,name,market_cap,sector`
   or adjust the loader's column mapping to match the CSV's actual headers —
   check the CSV first).
3. `services/investment_service.py`: when a stock holding is created/updated
   without a `market_cap`, look up `stock_master` by `symbol` and auto-fill
   `market_cap`/`sector`. Add `InvestmentService.lookup_stock(symbol)`.
4. `ui/dialogs/holding_dialog.py`: on symbol entry (stock type), auto-populate
   market cap/sector from `lookup_stock` if the user hasn't set them.
5. Tests: extend `tests/test_services/test_data_loader.py` to assert
   `stock_master` rows are loaded; add a unit test for `lookup_stock`.

**Acceptance:** `stock_breakdown_by_cap()` (already implemented in
`InvestmentService`) gets real data without manual `market_cap` entry for
known symbols.

---

## Phase 9 — Shared `MasterDetailView` / `TileListPanel` (Low priority, high payoff)

**Problem:** `accounts_view.py`, `goals_view.py`, `investments_view.py`,
`liabilities_view.py`, `income_view.py` each hand-roll: a scrollable tile list
on the left, a detail pane on the right, an "Add" button, and selection
wiring between the two.

**Plan:**
1. `ui/widgets/master_detail_view.py`: new `MasterDetailView(QWidget)` base
   providing:
   - `tile_container` (QVBoxLayout in a QScrollArea)
   - `detail_container` (QStackedWidget or QVBoxLayout placeholder)
   - `add_button` (QPushButton, connected via a constructor callback)
   - `set_tiles(widgets: list[QWidget])` / `clear_tiles()`
   - `show_detail(widget: QWidget | None)` (None → empty-state placeholder)
   - Hooks (`on_add`, abstract `build_detail(item)`)
2. Migrate **one view first** (suggest `liabilities_view.py` — smallest) to
   confirm the abstraction fits, then `goals_view.py`, `income_view.py`,
   `investments_view.py`, `accounts_view.py`.
3. Each migration should be its own commit/PR — this is pure refactor, so the
   existing UI smoke test (`test_main_window_loads_all_nav_pages`,
   `test_main_window_nav_switch`) plus the new per-view smoke tests (Phase 11
   below) are the regression safety net. No behavior change expected.

**Acceptance:** line count of the 5 views drops noticeably; `MainWindow`
smoke tests still pass; visual layout unchanged.

---

## Phase 10 — Versioned SQL migration framework (Low priority)

**Problem:** `db/migrate.py` has `SCHEMA_VERSION = 1` and a flat
`_additions()` dict — there's no ordered list of migration steps, so a future
rename/drop/retype has nowhere to go.

**Plan:**
1. Restructure `db/migrate.py`:
   ```python
   MIGRATIONS: list[tuple[int, Callable[[Database], None]]] = [
       (1, _migration_001_account_columns),  # wraps today's _additions() logic
       # (2, _migration_002_xxx), ...
   ]

   def run_migrations(db):
       _ensure_version_table(db)
       version = _current_version(db)
       for target_version, fn in MIGRATIONS:
           if version < target_version:
               fn(db)
               _set_version(db, target_version)
               version = target_version
   ```
2. Move the current `_additions()` ALTER TABLE logic into
   `_migration_001_account_columns` unchanged (no behavior change for existing
   databases — they're already at version 1).
3. `db/migrations/README.md`: update with the new convention — each future
   schema change adds one `_migration_NNN_<name>` function + one `MIGRATIONS`
   tuple entry. Keep migrations additive/idempotent (no destructive `DROP`
   without a backup step).
4. Tests: `tests/test_repositories` or a new `tests/test_db/test_migrate.py` —
   create a v0 DB (schema only, no `schema_version` row), run `run_migrations`,
   assert `schema_version.version == max(MIGRATIONS version)` and idempotent
   on a second call.

**Acceptance:** adding a new migration is "add one function + one tuple
entry"; running migrations twice is a no-op.

---

## Phase 11 — Surface XIRR per holding/portfolio (Medium priority)

**Problem:** `utils/calculators.xirr([(days_offset, cashflow), ...]) -> float`
exists and is tested but unused by any service or view.

**Plan:**
1. `services/investment_service.py`: add
   ```python
   def holding_xirr(self, holding: Holding) -> Optional[float]:
       """XIRR from purchase_date/invested_amount (outflow) to today/current_value (inflow)."""
   ```
   Return `None` if `purchase_date` or `invested_amount` is missing/zero.
   For SIP holdings (`sip_amount` set), build a monthly cashflow series from
   `purchase_date` to today instead of a single lump sum.
2. `services/investment_service.py`: add
   ```python
   def portfolio_xirr(self) -> Optional[float]:
       """Aggregate XIRR across all active holdings' cashflows."""
   ```
3. `ui/widgets/holding_tile.py` / `ui/views/investments_view.py`: show XIRR %
   on the holding tile/detail pane (e.g. "XIRR: 12.4%"); show portfolio XIRR
   as a KPI on `investments_view.py` or the dashboard.
4. Tests: `tests/test_services/test_investment_service.py::test_holding_xirr_*`
   covering lumpsum and SIP cases, plus a "missing data → None" case.

**Acceptance:** a holding with a purchase date and current value shows a
non-`None` XIRR; portfolio-level XIRR appears as a KPI.

---

## Phase 12 — Recurring transaction auto-posting (Medium priority)

**Problem:** Income has `pending_sources()` (recurring sources not yet logged
this month), but SIPs (`holdings.sip_amount`/`sip_day_of_month`), EMIs
(`liabilities.emi_amount`/`next_due_date`), and insurance premiums
(`holdings.premium_amount`/`premium_due_date`) have no equivalent — nothing
posts ledger transactions or reminds the user.

**Plan (mirror the income pattern):**
1. `services/investment_service.py`: `pending_sips(period_month) -> list[Holding]`
   — active SIP holdings with `sip_day_of_month` set and no matching
   transaction (`txn_type='expense'`, description/tag referencing the holding)
   for that month.
2. `services/liability_service.py`: `pending_emis(period_month) -> list[Liability]`
   — same idea using `next_due_date`.
3. A small "post this month's recurring items" action — could live on the
   Dashboard (a "Pending this month" panel listing income, SIPs, EMIs,
   premiums due, each with a one-click "Log now" that opens the relevant
   dialog pre-filled, reusing `IncomeService.record_month` as the template for
   `InvestmentService`/`LiabilityService` equivalents that post a transaction
   and bump `holdings.current_value` / `liabilities.outstanding`).
4. **Do not** auto-post silently — keep the existing pattern of
   user-confirmed, one-click logging (matches the "no surprises" data
   philosophy in README).
5. Tests: unit tests for `pending_sips`/`pending_emis` filtering logic
   (active vs inactive, already-logged-this-month vs not).

**Acceptance:** Dashboard shows a "Due this month" list combining income,
SIPs, and EMIs; clicking an item logs it without manual data re-entry.

---

## Phase 13 — Hard block on duplicate loan entry (Low priority)

**Problem:** `accounts_view.py` shows a reminder dialog if an account has loan
fields filled in, but a user can dismiss it and still have the same debt in
both `accounts` (descriptive `loan_*` fields) and `liabilities`.

**Plan:**
1. `services/account_service.py`: add `account_has_corresponding_liability(account_id) -> bool`
   — checks `liabilities.account_id == account_id` for any active row.
2. `accounts_view.py`: when saving an account with loan fields AND no linked
   liability exists, change the dialog from "reminder" to "reminder + offer to
   create the liability now" (prefilled `LiabilityDialog` from the account's
   loan fields). Still don't hard-block — but make the happy path one click.
3. Optional stricter mode (config flag) that refuses to save loan fields on an
   account if a liability with `account_id` pointing at it already exists
   (true double-entry) — raise `ValueError` from `AccountService.update_account`.
4. Tests: `tests/test_services/test_account_service.py` —
   `test_account_with_loan_fields_and_existing_liability_flagged`.

**Acceptance:** the existing reminder gains a one-click "Create liability"
action; true duplicates (same account_id in both places with loan fields) are
rejected or flagged programmatically, not just by a dialog the user can ignore.

---

## Phase 14 — Sustain ≥80% service test coverage

This pass (see accompanying test files) brings the previously-untested
services and repositories listed in `STATUS.md` up to baseline coverage:
`category_service`, `goal_service`, `income_source_service`,
`investment_service`, `liability_service`, `net_worth_service`,
`projection_service`, `data_persister`, and repositories `holding_repo`,
`liability_repo`, `goal_repo`, `goal_holding_repo`, `income_repo`,
`income_entry_repo`, `category_repo`.

**Going forward:** any new service/repository added per the README's "Adding a
new entity" playbook must ship with at least one CRUD test
(`tests/test_repositories/`) and one business-logic test
(`tests/test_services/`) in the same change — add this to the playbook section
of `README.md`.

---

## Suggested order

1. Phase 11 (XIRR) and Phase 12 (recurring) — most user-visible value, modest
   surface area, no schema changes.
2. Phase 8 (stock_master) — small, self-contained, removes dead code.
3. Phase 7 (FX) — needed before any non-INR account is realistically usable.
4. Phase 10 (versioned migrations) — do this *before* Phase 7/8 land their
   schema changes, so those changes go through the new framework.
5. Phase 9 (MasterDetailView) — pure refactor, do whenever there's a quiet
   window; biggest diff but lowest risk if the smoke tests pass.
6. Phase 13 (loan double-entry) — small, UX-only.
