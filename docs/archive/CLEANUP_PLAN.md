# Code Cleanup Plan — Personal Finance Manager

> **⚠️ SUPERSEDED (2026-07-03):** This plan is stale. See **`STATUS.md`** for
> the current, code-verified state of the project. Kept for historical context only.

**Last updated:** June 2026 — Phases 1–6 implemented.

---

## Completed

### Phase 1 — Test foundation ✅
- Shared `tests/conftest.py`, unit + smoke tests, `pytest.ini`, `run_tests.bat`
- **23 tests** passing

### Phase 2 — Layering consistency ✅
- `AppContext` wires all services; `MainWindow` injects into every view
- New services: `IncomeSourceService`, `LiabilityService`, `GoalService`, `CategoryService`
- `InvestmentService` extended with update/delete/toggle
- **Acceptance:** `ui/` has zero `from db.connection` / `from repositories` imports

### Phase 3 — Deduplicate UI patterns ✅ (partial)
- `ui/theme/badges.py` — shared badge colours (income, holdings, liabilities, goals)
- `ui/helpers/account_combo.py` — shared account filter reload
- Master/detail tile base class **deferred** (large refactor, low risk if deferred)

### Phase 4 — Data integrity & validation ✅ (partial)
- `utils/form_validation.py` wired into account section, transaction, and goal dialogs
- Goal ↔ holdings linking (already in `GoalDialog`; now via `GoalService`)
- Loan-field reminder on Accounts save when loan/CC fields are set
- Cross-currency FX aggregation **deferred** (document in README; use single currency)

### Phase 5 — Repository & migration hygiene ✅
- Split `other_repos.py` → `income_repo`, `income_entry_repo`, `liability_repo`, `goal_repo`, `goal_holding_repo` (re-exports kept)
- `schema_version` table + version tracking in `db/migrate.py`
- `tests/test_repositories/` — account + transaction CRUD smoke tests
- `db/migrations/README.md` documents migration approach

### Phase 6 — Documentation sync ✅
- README: setup.bat, run_tests.bat, backup count (30), removed stub-view section
- VALIDATION_REPORT: linking, tests, layering updates
- This file updated

---

## Remaining (optional follow-ups)

| Item | Priority |
|------|----------|
| Extract `MasterDetailView` / `TileListPanel` base widget | Low |
| FX rates table + conversion in aggregations | Medium |
| `stock_master` table in `schema.sql` | Low |
| Versioned SQL migration files in `db/migrations/` | Low |
| ≥80% coverage on `services/` | Medium |
| Hard block duplicate loan in accounts + liabilities | Low |

---

## Test strategy

```bat
run_tests.bat              # all 23 tests
run_tests.bat -m smoke     # E2E + UI only
```

| Layer | Location |
|-------|----------|
| Unit | `tests/test_utils/`, `tests/test_services/` |
| Repositories | `tests/test_repositories/` |
| E2E smoke | `tests/test_smoke/test_e2e_session.py` |
| UI smoke | `tests/test_smoke/test_app_launch.py` |
