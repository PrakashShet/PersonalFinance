# Status - Personal Finance Manager

**Single source of truth for the current state of this project.** Update this file in
place; don't add another planning document. Superseded plans live in `docs/archive/`.

- Architecture and conventions → `CLAUDE.md`
- Setup and usage → `README.md` and the user guide (`docs/user-guide/`)
- What changed in each version → `CHANGELOG.md`
- Task playbooks → `docs/skills/`

**Last verified against the code:** 2026-11-06 (version 1.1.0, store format v2).

---

## Health

Verified this pass, by running things - not asserted:

- **Test suite executed on Windows: 147 passed** (`run_tests.bat`). Includes hand-worked
  budget numbers, a save → reload round trip for budgets, a smoke test that drives the
  Budgets page, the Dashboard alert, the expense-dialog hint and *See transactions*, and
  a regression test that coloured (toned) labels really show their colour.
- `compileall` clean; layering rule holds (no `db` / `repositories` imports in `ui/`); no
  hex colours in Python; no unused imports in the files changed for 1.1.
- Every page reviewed in **both themes**: on a copy of the real store with demo budgets
  added (`tools/render_pages.py`), and on the fictional demo household.
- `tools/make_demo_store.py` builds a store that `check_store.py` passes with no
  findings; the user guide's screenshots are generated from it.
- `tools/privacy_scan.py --history`: no personal values in any publishable file or in the
  committed history.
- The live store was audited read-only: format v2, every balance matches its ledger. It
  has no `budgets.json` yet - the app creates it (empty) on its next start.

Not verified: the PyInstaller `.exe` has **not been rebuilt** since 1.0, so the
`%APPDATA%` data location and the one-time import from the old beside-the-exe folder are
tested only by reading the code. Run `run_build_exe.bat` and launch it once.

---

## Done in 1.1

| Area | Change |
|------|--------|
| Budgets | Monthly or yearly limit per expense category; Budgets page (spent, left, per-day allowance, last 6 months / 3 years, spending without a limit); limit suggested from recent spending; hint in the expense dialog; *Needs attention* alerts; calendar or financial year (Settings); audit checks |
| Colours | Red / green values on KPI, stat, row and tile labels never showed (an `#id` rule outranked `[tone]`) - fixed for every page, with a regression test |
| Layout | A long selected option in a segmented control lost its last letters; detail-panel sections sat 9 px off the header - both fixed |
| Shortcuts | Ten pages: Ctrl+1 … Ctrl+9 and Ctrl+0 (an eleventh page would get none; a test guards it) |
| Docs | User guide with screenshots of a fictional household; skills for budgets, the user guide and releasing; MIT license; changelog |
| Publishing | Privacy scan tool; demo-data generator; `.gitattributes`; personal figures removed from docs and tests |

The two live-data steps from 1.0 (removing the test accounts, upgrading the store to
format v2) were completed on 2026-11-06.

---

## Closed in 1.0

| Was | Fix |
|-----|-----|
| Non-atomic store writes | Temp file + `os.replace`; unchanged files not rewritten; refuses to empty a large file |
| Damaged file → overwritten 60 s later | Store validated before anything loads; app stops with recovery steps, nothing written |
| No version control | git repo; personal data excluded from it |
| Projections never spent the portfolio | Deficits paid from cash then investments; post-retirement return used; "runs out at age X" shown |
| Balances not explained by transactions | Ledger invariant (format v2): opening balances and hand edits become `adjustment` entries; Reconcile action; audit check |
| Opening balances counted as income | `adjustment` type, excluded from income/spending/savings |
| Dashboard trend chart & reminders never rendered (`db` NameError hidden by `except: pass`) | Service methods; dashboard failures are logged, never swallowed |
| Term insurance in investment returns (permanent −100% "worst mover") | Reported separately as *protection* |
| `xirr` unhardened, unused | Raises on invalid input, bisection fallback; surfaced per holding and portfolio |
| `fv_of_sip` docstring wrong | Documented as annuity-due, with its exact inverse |
| No FX layer | `fx_rates` table; balances without a rate are reported, never summed as rupees |
| No `stock_master` table | Table + seed load; typing a symbol fills market cap / sector |
| No `MasterDetailView` base | Five list pages share one base; six tile classes became one `ListTile` |
| Additive-only migrations | Versioned JSON store migrations (`services/store_migrations.py`); SQLite rebuilt in memory each launch |
| No recurring posting | *Needs attention*: SIPs, EMIs, premiums, income, maturities, reminders - one-click logging that also updates the holding / loan |
| Loan double-entry soft warning | Account shows whether its loan is tracked; one click creates the linked liability |
| `.exe` data inside `dist/` (wiped by rebuild) | `%APPDATA%\PersonalFinanceManager`; old location imported once |
| Backups: 30 newest, same disk, shutdown only | Startup + shutdown + manual; tiered retention (30 newest + daily/monthly/yearly); optional second-copy folder |
| Two app copies could overwrite each other | Single-instance lock |
| Old DBs' nulls in `NOT NULL` columns made a fresh load crash | Loader applies the column default |
| Dark-only theme with ~140 hardcoded colours | Light / dark / match Windows; tokens + one stylesheet template; validated chart palette |

---

## Open gaps

| # | Gap | Notes |
|---|-----|-------|
| 1 | `.exe` not rebuilt or tested since 1.0 | See Health |
| 2 | Spending history is sparse | Projections use the last six months of logged expenses, so they stay optimistic until spending is logged regularly; the page warns |
| 3 | No price / NAV refresh | By design (no network). Update values by hand |
| 4 | Credit-card account balance sign is undefined | Treat card debt as a liability; card *accounts* are excluded from cash totals |
| 5 | Categories are fixed | No screen to add or rename categories (budgets can only use the seeded ones); new seed categories never reach existing stores |
| 6 | Budget limits have no history | Past periods are compared with today's limit; no rollover of unspent amounts |
| 7 | UI tests are smoke-level | Pages build, switch and re-theme with data; budgets are driven end to end; other dialogs are not click-tested |
| 8 | Old dialogs (goal, holding, income, liability) keep their dense forms | Restyled, not redesigned |

---

## Environment note

Tests need the project's Windows `.venv` (PyQt6 + pytest-qt). `tests/conftest.py`
points `PFM_HOME` at a temporary folder, so tests never touch real data or logs.
A Linux sandbox can still run `compileall`, the layering grep and `check_store.py`.
