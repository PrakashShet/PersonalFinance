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

- **Test suite executed on Windows: 167 passed** (`run_tests.bat`, about 30 s). Besides the
  unit tests it now runs four end-to-end suites through the real window and dialogs
  (every dialog's own Save button and validation run; a dialog left open fails):
  - `test_e2e_user_session` - one session across every page: accounts, transactions
    (add, add-another, edit, duplicate, delete, search), budgets, income, SIP, term
    insurance, stock look-up, EMI, goals, reminders, premium, exchange rate, theme,
    backups and copy folder, projections, Ctrl+0 - then save, reopen from the files
    in a fresh database, and `check_store.py` must report nothing. Balances are worked
    out by hand at every step.
  - `test_e2e_edit_fidelity` - for every record in the demo household, Edit then Save
    without changes must leave the record identical.
  - `test_e2e_more_flows` - every *New* menu entry, every form's validation message,
    one-click SIP / EMI logging from the Dashboard, Reconcile, Track in Liabilities,
    *Add budget* from the banner, the backup copy folder, and a 3,000-row ledger
    staying responsive through a theme change.
  - `test_e2e_startup` - the real `main.py` in a child process: first start, a second
    copy, a damaged file, a newer data format, an old-format upgrade, a leftover
    `app.db`, data from beside an old `.exe`, a hard kill and relaunch, and an error
    inside a handler (reported, app keeps running).
- **Scale:** a synthetic 30-year store (35,000 transactions, 6,000 snapshots) opens in
  0.3 s, builds its window in 0.3 s, refreshes any page in under 0.1 s, shows *All
  time* in 0.7 s, switches theme in 0.6 s and saves a change in 0.4 s.
- **The `.exe`:** built with the project's spec (into a scratch folder) and launched
  off-screen with throwaway data folders: first start, relaunch after a hard kill,
  import of data kept beside an old build, killed before its first save, and a store
  left with no categories by the old bug (it heals). The build script's set-aside of
  beside-the-exe data was checked for a successful and a failed build.
- `compileall` clean; layering rule holds; no hex colours or hand-built ₹ strings in
  Python; no unused imports in any Python file in the repo.
- Every page reviewed in **both themes**; the changed dialogs looked at as well.
- `tools/privacy_scan.py --history`: no personal values in any publishable file or in
  the committed history.
- The live store was audited read-only: format v2, every balance matches its ledger.

Not verified: a person clicking through the built `.exe` on the desktop (it was
launched off-screen only), and macOS / Linux.

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
| End-to-end testing | Found and fixed: SIP / mutual fund form crashed the app; unexpected errors closed the app silently (now reported); a long ledger froze the app for minutes on a theme change; categories lost for good if the app closed within a second of its first start; Edit + Save erased creation dates and invented dates / zeroed a card's principal; three forms ignored Save silently; rebuilding the `.exe` deleted beside-the-exe data; "Rs" and Western grouping in two forms; batch files named a missing script; the lock file was visible to git |

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
| 1 | The `.exe` is tested off-screen only | Built and launched in five scenarios (see Health); not clicked through by a person on the desktop |
| 2 | Spending history is sparse | Projections use the last six months of logged expenses, so they stay optimistic until spending is logged regularly; the page warns |
| 3 | No price / NAV refresh | By design (no network). Update values by hand |
| 4 | Credit-card account balance sign is undefined | Treat card debt as a liability; card *accounts* are excluded from cash totals |
| 5 | Categories are fixed | No screen to add or rename categories (budgets can only use the seeded ones); new seed categories never reach existing stores |
| 6 | Budget limits have no history | Past periods are compared with today's limit; no rollover of unspent amounts |
| 7 | End-to-end tests drive dialogs through their handlers | Every page and form is exercised and its Save button clicked, but menus, mouse clicks on tiles and keyboard focus are not simulated |
| 8 | Old dialogs (goal, holding, income, liability) keep their dense forms | Restyled, not redesigned |

---

## Environment note

Tests need the project's Windows `.venv` (PyQt6 + pytest-qt). `tests/conftest.py`
points `PFM_HOME` at a temporary folder, so tests never touch real data or logs.
A Linux sandbox can still run `compileall`, the layering grep and `check_store.py`.
