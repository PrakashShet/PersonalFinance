# CLAUDE.md — Personal Finance Manager

Context for AI assistants working in this repo. Read this first.

**What this is:** a single-user PyQt6 desktop app for tracking accounts, transactions,
budgets, income, investments, liabilities, goals, and long-horizon projections. Indian
locale (₹, lakhs/crores). Python, no server, no network calls. Version 1.1, store format
v2. MIT-licensed; the repo is meant to be publishable, so **personal data never enters it**
(see *Publishing* below).

**Design horizon:** the user intends to run this for 25–30 years. Decisions should
favour data durability and readable-in-20-years file formats over cleverness.

---

## Architecture

```
ui  ──►  services  ──►  repositories  ──►  db (SQLite in memory)
              └─►  models                     ▲
                                              │
        services/storage.py ──────────────────┘   (reads/writes data/store/*.json)
```

**The one hard rule: `ui/` must never import from `db/` or `repositories/`.**
Views receive an `AppContext` and call services only. Verify with:

```bash
grep -rn "from db\|from repositories" ui/     # must return nothing
```

If a view needs data that no service exposes, add a service method or an
`AppContext` helper, never a repository import.

| Layer | Contains | Never does |
|-------|----------|------------|
| `models/` | Dataclasses, one per table, inherit `BaseModel` | Business logic, SQL |
| `repositories/` | Thin SQL; most subclass `BaseRepository[T]` | Cross-entity logic |
| `services/` | All business logic; the UI's entry point | Qt imports (except `app_context.py`, which owns the signal bus) |
| `ui/` | Qt widgets only | SQL, repo/db access, hardcoded colours |

Key service modules: `storage.py` (open/save/backup lifecycle), `ledger.py` (balance
rules, pure), `store_migrations.py` (JSON format versions), `recurring_service.py`
(what's due + one-click logging), `budget_service.py` (spending limits per category),
`fx_service.py`, `preferences_service.py`.

---

## Data model: JSON is the source of truth, SQLite is scratch

```
open:  read + validate every store file ─► (backup, migrate) ─► fresh in-memory SQLite ─► startup backup
save:  SQLite ─► data/store/*.json   (atomic, only changed files)
close: save ─► shutdown backup
```

- SQLite is `:memory:` and rebuilt from JSON on every launch. A schema change never
  needs an SQLite migration. (Older versions kept `data/app.db`; `main.py` deletes it.)
- **Reads fail closed.** `data_loader.read_store` raises `StoreLoadError` for a file that
  won't decode/parse, isn't a list of objects, is empty, or has fields the schema doesn't
  know. Nothing is written; `main.py` shows recovery steps and quits. Never "skip" a bad
  file - a skipped table gets saved back as empty.
- **Writes are atomic** (`utils/json_handler.write_text_atomic`: temp file, fsync,
  `os.replace` with retries). `DataPersister` reads every table before writing any, skips
  unchanged files, and refuses to replace ≥10 records with an empty table (`SaveRefused`).
- Saves follow every change (`ui/autosave.py`: 0.8 s debounce on `events.changed`) plus
  a 60 s timer that also records the daily net-worth snapshot.
- `STORE_LOAD_ORDER` (`data_loader.py`) is ordered for foreign keys; `STORE_DUMP_ORDER`
  (`data_persister.py`) mirrors it. **A new table goes in both.**
- A `null` in a column declared `NOT NULL DEFAULT x` loads as `x` (older DBs added
  those columns without the constraint, so real stores contain such nulls).

### Store format versions

`data/store/_meta.json` holds `store_version`. A store with data and no meta file is v1.
`services/store_migrations.py` holds ordered migrations over the in-memory tables; they
run after a `pre-migration-vN` backup, and the result is written back **only after it has
loaded successfully**. A store newer than the app is refused (`StoreVersionError`).
Renames, retypes and backfills belong here - see the module docstring for the recipe.

- **v2** - ledger invariant (below): opening-balance income → `adjustment`; opening and
  reconciliation entries added so every active account's balance equals its ledger.

### Backups

`data/user/backups/<YYYYMMDD_HHMMSS>[_label]/`: at startup (`startup`), before an upgrade
(`pre-migration-v2`), at shutdown (`shutdown`), on demand (`manual`). Identical-to-newest
copies are skipped. Retention (`backups_to_keep`, pure): newest 30 + newest per day for
30 days + per month for 24 months + per year forever; `manual`/`pre-migration` forever.
Optional mirror folder (`preferences.backup_mirror_dir`). Restore = copy a backup's files
into `data/store/` with the app closed.

### Paths

`config/settings.py`: `PFM_HOME` env var → else frozen `.exe` → `%APPDATA%\PersonalFinanceManager`
→ else project root. Seed / reference / schema / stylesheet come from the bundle. Tests set
`PFM_HOME` to a temp dir in `tests/conftest.py` before importing settings.

---

## The ledger invariant (store v2)

For every active account: `current_balance == Σ ledger.effects(txn)` over its transactions.

- `services/ledger.py` is the single definition (income/sell +, expense/buy −, transfer
  −/+, **`adjustment` signed**). `TransactionRepository.ledger_balances` mirrors it in SQL;
  `check_store.py` mirrors it in plain Python (no imports, on purpose). Change all three together.
- **Never write `current_balance` directly from a service.** Opening balance → adjustment
  (`create_account`); a hand-edited balance → adjustment (`update_account`/`set_balance`);
  an unexplained difference already in the balance → `record_reconciliation` (inserts the
  entry *without* moving the balance).
- Adjustments are excluded from income/spending/savings (`TransactionService.summary`
  only reads income, expense and investment keys).

---

## Bootstrap (`main.py`)

1. `QApplication`; `PreferencesService(settings.PREFS_PATH)`; `theme.install(app, mode)`
2. Single-instance `QLockFile(settings.LOCK_PATH)` - a second copy would overwrite saves
3. Import legacy beside-the-exe data (once), delete legacy `app.db`
4. `db.connect(":memory:")`; `Storage(...).open()` - `StoreLoadError`/`StoreVersionError`/
   anything else → message box, exit, nothing written
5. `AppContext.create(db, preferences=, storage=)` → `MainWindow` → `AutoSaver`
6. `aboutToQuit` → `storage.close()` (final save + shutdown backup)

---

## UI conventions

**Theme.** `ui/theme/tokens.py` (LIGHT/DARK dicts) → `ui/resources/styles/theme.qss`
(`$token` placeholders) → `ThemeManager` (`ui/theme/manager.py`, singleton `theme`):
Fusion style + palette + rendered stylesheet; follows Windows or a saved choice.
- **No hex colours in Python.** Style via object names and the `tone` / `kind` / `selected`
  properties (`QLabel#badge[tone="positive"]`, `QPushButton[kind="primary"]`). For painting
  use `theme.qcolor("token")`, and connect `theme.changed` to repaint.
- Chart colours are the validated categorical slots `series_1..5`, assigned by entity in a
  fixed order (`ALLOC_ORDER`), never by rank. Charts ship a labelled legend/table.
- **Tones on role labels:** an `#id` rule outranks a bare `[tone]` rule, so every label
  role that takes a tone (`statValue`, `kpiValue`, `rowValue`, `tileValue`, `fieldHint`...)
  is listed in the tone block of `theme.qss`. A new toned role goes there too.
- Icons: `ui/theme/icons.py` (inline SVG, tinted per theme). No image files.

**No flicker.** Never `show()` / `setVisible(True)` a widget before it has a parent:
on Windows it opens as a window of its own for a moment. Hide when needed (a child shows
with its parent). Remove widgets with `discard()` / `clear_layout()` (`ui/widgets/common.py`),
which hide before detaching: a widget added to a visible container has a show queued, and
if it is detached first it pops up as a window. `test_no_widget_flashes_up_as_a_window_of_its_own`
and `test_start_up_opens_one_window_and_paints_it_before_saving` guard both.

**Building blocks** (`ui/widgets/`): `Card`, `PageHeader`, `KpiCard`, `Badge`, `Banner`,
`EmptyState`, `SegmentedControl`, `StatGrid`, `ActivityRow`, `ElidedLabel`, `ListTile`,
`DetailPanel`, `TrendChart`, `SegmentedBar`, `Toast`. Single-line text that can be long
(names, notes) must be an `ElidedLabel` - plain labels widen the page past the window.

**Pages.** List pages subclass `ui/views/master_detail.MasterDetailView` (hooks: `fetch`,
`make_tile`, `render_detail`, `refresh_kpis`, `on_add`...). Register in `NAV` in
`ui/main_window.py` as `(key, label, icon, cls)`; order = sidebar order = shortcut
(`nav_shortcut`: Ctrl+1…9, Ctrl+0 for the tenth). Ten pages exist; an eleventh would get
no shortcut. Wording shared across pages lives in `ui/helpers/` (e.g. `budget_text.py`).

**Refresh.** Services call `on_change(topic)` → `events.changed` → each page sets `_dirty`
for topics in `_topics`. The **visible** page refreshes itself ~60 ms after a change
(`MainWindow._live`); others refresh when opened (`ensure_fresh`). A service that mutates
without `on_change` leaves pages stale *and* skips the save-after-change.

**Cross-page.** `ui.navigation.go("transactions", account_id=3)` → target `show_with()`.
`ui.widgets.toast.notify("Saved")` for confirmations. Dialogs return data; the page saves.

---

## Conventions and gotchas

- **`BaseRepository.insert` drops `None` values; `update` does not** - except
  `created_at`, which `update` never writes (the database sets it once; dialogs build
  fresh objects without it, which used to blank it on every edit).
- **Optional dates use `ui/widgets/date_field.DateField`**, which shows *Not set* and
  returns `None`. A plain `QDateEdit` always holds a date, so Edit + Save invented one.
  `test_e2e_edit_fidelity` fails if any dialog changes a record it only re-saved.
- **Seeded tables** (`SEEDED_TABLES` in `data_loader.py`, i.e. categories): an empty
  store file never wipes the seed rows, and `Storage.open` saves a new store at once -
  otherwise a close within a second of the first start left no categories, for good.
- **Errors in handlers:** `main.py` installs an error hook, so an exception escaping a
  slot is logged and reported instead of aborting the app (PyQt6's default). It's a
  safety net: still catch expected errors (`ValueError` from a service) in the view and
  show a `QMessageBox`.
- **Big tables:** fill a `QTableWidget` with updates off and columns not resizing to
  contents, then fit once (`TransactionsView.refresh`) - per-cell fitting is rows x rows
  and froze the app for minutes with a few years of history.
- **Money formatting:** `utils/formatters.py` - `fmt_inr(x, compact=, decimals=)`,
  `fmt_money(x, currency)`. Negative is `−₹1,234.00` (true minus before the symbol).
  Never hand-roll ₹ strings; Indian grouping (1,23,45,678) isn't `f"{x:,}"`.
- **Financial math** in `utils/calculators.py` is pure. `fv_of_sip` is an annuity-due and
  `required_monthly_sip` its exact inverse - change both or neither. `xirr` raises
  `ValueError` when no rate exists; callers return `None`.
- **Investments vs protection:** `term_insurance` is never in invested/value/returns
  (`InvestmentService.investments()`, `protection_summary()`).
- **XIRR flows:** linked buy/sell transactions plus any recorded cost they don't explain,
  dated at `purchase_date`; under 90 days of history → no annual figure.
- **FX:** `fx_rates` (store file) converts non-INR account balances. A balance without a
  rate is reported in `BalanceSheet.unconverted`, never summed as rupees.
- **Recurring logging** tags transactions (`sip:<id>:<YYYY-MM>`, `emi:...`, `premium:...`)
  so an instalment is offered once. Projections exclude `emi:` expenses (EMIs are
  projected from the amortisation schedule).
- `total_balance`/cash excludes `credit_card` accounts; debt lives in `liabilities`.
- **Budgets:** spending = `expense` transactions in the budget's category during the
  period, FX-converted (no rate → `unconverted`, never summed). A month is a calendar
  month; a year starts at the `budget_year_start` preference (1 = Jan, 4 = Apr / FY).
  One limit per (category, period) - `set_limit` replaces. Near from 80 %, over above the
  limit. Details: the **budgets** skill.

---

## Commands

```bat
run_setup.bat            :: create .venv, install requirements
run.bat                  :: launch the app
run_tests.bat            :: full pytest suite (169 tests, ~30 s; includes the end-to-end suites)
run_tests.bat -m smoke   :: E2E + UI smoke only
run_build_exe.bat        :: PyInstaller build via personal_finance.spec
```

```bash
python -m compileall -q -x '(\.venv|build|dist)' .        # syntax
grep -rn "from db\|from repositories" ui/                 # layering rule
python docs/skills/data-hygiene/check_store.py            # read-only data audit
python tools/render_pages.py --out shots                  # every page, both themes, on a temp COPY (never commit)
python tools/make_demo_store.py <new-folder>              # fictional household, for trying things
python tools/make_user_guide.py                           # regenerate docs/user-guide/images from demo data
python tools/privacy_scan.py --history                    # before any push: no personal data in the repo
```

Tests need PyQt6 + pytest + pytest-qt (the Windows `.venv`). They cannot run in a Linux
sandbox; say so rather than implying they passed.

End-to-end tests (`tests/test_smoke/test_e2e_*.py`) drive the real window: a `Robot`
replaces `QDialog.exec` with a scripted handler that fills a dialog and clicks its real
Save button (so validation runs); message boxes are recorded; a dialog left open fails.
`test_e2e_startup` runs the real `main.py` in a child process (`main_runner.py`). A new
dialog belongs in `test_e2e_edit_fidelity`; a new user flow in `test_e2e_user_session`.
`tests/conftest.py` destroys every window after each test, so no test leaks into the next.

---

## Repo layout

```
main.py                  Bootstrap → Qt → shutdown
config/                  settings.py (paths, PFM_HOME), constants.py, account_fields.py
db/                      connection.py, schema.sql, migrate.py (legacy, additive)
models/ repositories/    One per table (+ reference_repos.py: fx, stock master, reminders)
services/                Business logic, storage, ledger, migrations, app_context.py
ui/  main_window.py      Sidebar, quick-add, theme switch, save status
     views/              One per nav item + master_detail.py base
     widgets/            Shared building blocks (common.py, charts.py, ...)
     dialogs/            Add/edit modals (+ quick_dialogs.py)
     theme/              tokens.py, manager.py, icons.py, badges.py (labels + tones)
     resources/styles/theme.qss   Stylesheet template
     helpers/            Shared UI wording/helpers (budget_text.py, account_combo.py)
utils/                   calculators, formatters, json_handler (atomic writes), logger
tools/                   render_pages.py, make_demo_store.py, make_user_guide.py, privacy_scan.py
data/                    seed/ + reference/ (ship), store/ (SOURCE OF TRUTH), user/, cache/
tests/                   conftest.py + test_services/ test_repositories/ test_smoke/ test_utils/
docs/user-guide/         The user guide (README.md + images/ from demo data)
docs/skills/             Task playbooks (see below)
docs/archive/            Superseded planning docs
LICENSE CHANGELOG.md     MIT license; release notes
```

---

## Current state

`STATUS.md` is the single current-state document (health, closed and open gaps).
`CHANGELOG.md` records what each version changed, for users.

## Publishing

The repo is MIT-licensed and safe to push **only because personal data stays out of it**:
`data/store/`, `data/user/`, `logs/` and `shots/` are git-ignored. So:

- Never put real figures, names or paths from the user's data into code, tests, docs or
  commit messages - not even as an example. Use the demo household instead.
- Images in the repo come from `tools/make_user_guide.py` (demo data) only.
- The built app is committed in `dist/PersonalFinanceManager/` (the `.exe` and `_internal`)
  so people can run it without Python. `.gitignore` admits only that folder and never the
  `data/` or `logs/` an old build keeps beside its `.exe`. Rebuild (`run_build_exe.bat`) and
  commit it for each release, from the tagged commit.
- Before any push run `python tools/privacy_scan.py --history` - the **release** skill.

## Working agreements

- **Don't claim tests pass if you didn't run them.** Say which checks you actually ran.
- **Don't add another planning document.** Update `STATUS.md`; archive rather than accumulate.
- **Respect the layering rule** and **the ledger invariant**.
- **New table? Touch both load and dump orders.** Changing a record's shape or meaning?
  Add a store migration.
- **Mutating service? Call `on_change(topic)`.**
- **No colours in Python.** Add a token, use it via QSS or `theme.qcolor`.
- This is real personal financial data. Prefer additive, reversible changes; never modify
  `data/store/` without the user's go-ahead, and back it up first. Work on a copy
  (`PFM_HOME` / `tools/render_pages.py`) or the demo (`tools/make_demo_store.py`).
- **Visible change? Update the user guide** (text and images) - the **user-guide** skill.

## Project skills

Task-specific playbooks live in `docs/skills/`. Read the relevant one before starting:

| Skill | Use when |
|-------|----------|
| `docs/skills/add-entity/` | Adding a new tracked record type (table + model + repo + service + view) |
| `docs/skills/add-view/` | Adding or editing a page; theming; debugging stale pages |
| `docs/skills/verify-changes/` | Before calling any change done |
| `docs/skills/data-hygiene/` | Numbers look wrong; after bulk edits; periodic data audit |
| `docs/skills/budgets/` | Changing how spending limits work, or a budget figure looks wrong |
| `docs/skills/user-guide/` | After a visible UI change; keeping the guide and screenshots current |
| `docs/skills/release/` | Version bump, changelog, privacy scan, commit and push |

`docs/skills/` is the source. To load them as Claude Code skills, copy the tree to
`.claude/skills/` (git-ignored, so re-copy after editing a skill):

```bat
xcopy docs\skills .claude\skills\ /E /I /Y
```
