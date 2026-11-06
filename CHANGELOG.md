# Changelog

What changed in each version, newest first. The data format version (`store_version`
in `data/store/_meta.json`) is listed when it changed; older data is upgraded
automatically, after a backup, the first time a new version opens it.

## 1.1.0 - 2026-11-06

### New: budgets

- Set a **monthly or yearly spending limit** for any expense category on the new
  **Budgets** page (also *New → Budget*). A category can have both.
- Each budget shows what you've spent, what's left and about how much you can still
  spend per day (or per month for yearly limits), plus the last 6 months (or 3 years)
  against the limit. It is marked **Near limit** from 80% and **Over limit** once
  exceeded.
- When you add a budget, the app suggests a limit from your recent spending in that
  category.
- While you type an expense, the form shows what would be left of that category's
  budget.
- Budgets over or near their limit appear under **Needs attention** on the Dashboard.
- A banner lists this month's spending in categories that have no limit.
- **Yearly limits** can follow the calendar year or the Indian financial year (April
  to March): *Settings → Budgets*.
- *See transactions* opens the ledger filtered to the budget's category and period.
- The data audit (`check_store.py`) checks budgets too.
- New data file `budgets.json`, created empty on first start. The data format stays
  v2, so no upgrade step is needed.

### Fixed

- Red and green figures (gains, losses, money still needed, values over a limit)
  showed as plain text on cards, stat grids, rows and tiles across the app. They now
  show their colour, and a test keeps it that way.
- A long selected option in a segmented control lost its last letters.
- Sections in the detail panel were indented differently from their heading.
- Budget totals are shown in exact rupees, so *spent + left* adds up to the limit.
- `run.bat` named the wrong setup script in its error message.

### Other

- Keyboard: **Ctrl+0** opens the tenth page (Settings).
- A user guide with screenshots ([docs/user-guide](docs/user-guide/README.md)), made
  from a fictional demo household (`tools/make_demo_store.py`).
- `tools/privacy_scan.py` checks that none of your data is in the repository before
  you push.
- Released under the MIT license.

## 1.0.0 - 2026-11-06

A rebuild of the app's foundations and interface.

- **Data safety.** Saves are atomic (temporary file, then swap) and happen within a
  second of every change. A damaged file stops the app instead of being overwritten.
  Only one copy can run at a time. Backups are taken at start-up and shutdown and
  kept on a tiered schedule (latest 30, daily for a month, monthly for two years,
  yearly forever), with an optional second copy in another folder. The data format
  is versioned and upgrades itself after a backup.
- **Correct balances (data format v2).** Every account balance equals the sum of
  its transactions. Opening balances and hand edits are recorded as *adjustments*,
  which are never counted as income.
- **Projections** spend down savings after retirement and say when money would run
  out.
- **Investments** show a timing-aware annual return (XIRR). Term insurance is kept
  separate as *protection*.
- **New:** a *Needs attention* list with one-click logging of SIPs, EMIs and
  premiums, exchange rates for accounts in other currencies, stock symbol look-up,
  and turning an account's loan details into a tracked liability.
- **A new interface:** light, dark and *Match Windows* themes, type-first
  transaction entry, *Update balance*, and one consistent list-and-details layout
  for every list page.
- The `.exe` keeps its data in `%APPDATA%\PersonalFinanceManager` (a rebuild no
  longer wipes it). Data from older builds is imported once.

## Before 1.0

Early development. The superseded plans are kept in `docs/archive/`.
