# CLAUDE.md — Personal Finance Manager

Context for AI assistants working in this repo. Read this first.

**What this is:** a single-user PyQt6 desktop app for tracking accounts, transactions,
income, investments, liabilities, goals, and long-horizon projections. Indian locale
(₹, lakhs/crores). ~12k LOC Python, no server, no network calls.

**Design horizon:** the user intends to run this for 25–30 years. Decisions should
favour data durability and readable-in-20-years file formats over cleverness.

---

## Architecture

```
ui  ──►  services  ──►  repositories  ──►  db
              └─►  models                   ▲
                                            │
             data_loader / data_persister ───┘   (reads/writes data/store/*.json)
```

**The one hard rule: `ui/` must never import from `db/` or `repositories/`.**
Views receive an `AppContext` and call services only. This is currently clean —
verify with:

```bash
grep -rn "from db\|from repositories" ui/     # must return nothing
```

If a view needs data that no service exposes, add a method to the service (or an
`AppContext` helper), never a repository import.

### Layer responsibilities

| Layer | Contains | Never does |
|-------|----------|------------|
| `models/` | Frozen-ish dataclasses, one per table. Inherit `BaseModel` for `to_dict` / `from_row` / `from_dict`. | Business logic, SQL |
| `repositories/` | Thin SQL. Subclass `BaseRepository[T]`, set `table_name` + `model_class`. | Cross-entity logic |
| `services/` | All business logic. Entry point for the UI. | Qt imports (except `app_context.py`, which owns the signal bus) |
| `ui/` | Qt widgets only. | SQL, direct repo/db access |

---

## Data model: JSON is the source of truth, SQLite is scratch

```
boot:  data/store/*.json  ──►  DELETE FROM <table>  ──►  INSERT  (SQLite)
save:  SQLite             ──►  data/store/*.json    (+ timestamped backup)
```

`data/app.db` is **disposable** — deleting it loses nothing, it is rebuilt from JSON
on next boot. The JSON files under `data/store/` are the real data.

Consequences to keep in mind:

- `DataLoader.load_store_data` does a **full wipe-and-refill** per table. Anything
  written directly to SQLite without a corresponding dump is lost on next boot.
- `STORE_LOAD_ORDER` (in `services/data_loader.py`) is ordered **for FK satisfaction**.
  `STORE_DUMP_ORDER` (in `services/data_persister.py`) mirrors it. Adding a table
  means adding it to **both**, in a position that respects foreign keys.
- Autosave runs every `AUTOSAVE_INTERVAL_SEC` (60s, `config/settings.py`) with
  `make_backup=False`. Backups are made only on clean shutdown.
- Backups: `data/user/backups/<YYYYMMDD_HHMMSS>/`, last `MAX_BACKUPS` (30) retained.
  To restore: copy a backup folder's contents over `data/store/` and relaunch.

### Known durability weakness

`DataPersister.dump_store_data` writes each JSON file with `out_path.write_text(...)`
directly over the live file. A crash mid-write truncates that file, and autosave
re-runs this every 60s without a backup. **If you touch that function, make the write
atomic** (write to `<name>.tmp` then `os.replace`).

---

## Bootstrap sequence (`main.py`)

1. `db.connect(settings.SQLITE_PATH)` — WAL mode, FK enforcement on
2. `db.apply_schema(settings.SCHEMA_PATH)` — `schema.sql`, all `CREATE TABLE IF NOT EXISTS`
3. `run_migrations(db)` — additive `ALTER TABLE ADD COLUMN` only (see below)
4. `loader.load_seed_data(SEED_DIR)` — categories, stock master; only if table empty
5. `loader.load_store_data(STORE_DIR)` — the user's records; wipe-and-refill
6. `loader.load_reference_data(REFERENCE_DIR)` — tax slabs, assumptions → `reference_data` table
7. `MainWindow()` → sidebar + `QStackedWidget`
8. `QTimer` autosave started; `app.aboutToQuit` → `shutdown()`

## Migrations

`db/migrate.py` is **additive only** — it can add columns, nothing else. Because
`schema.sql` uses `CREATE TABLE IF NOT EXISTS`, a column added to `schema.sql`
does *not* reach an existing database; it must also be listed in `_additions()`.

`SCHEMA_VERSION` is a single hardcoded int (currently `1`) and `db/migrations/`
holds only a README. There is **no framework for renames, drops, or retypes** —
if you need one, that is a real piece of work, not a one-liner.

Account detail columns are generated from `config/account_fields.py::column_additions()`
so the model, DB, and UI cannot drift. Add account fields there, not by hand.

---

## Conventions and gotchas

**`BaseRepository.insert` drops `None` values; `update` does not.** Insert lets DB
defaults apply, update writes explicit `NULL`. If a round-trip appears to blank a
column, this asymmetry is why.

**Cross-tab refresh is a signal bus, not polling.** `AppContext.events` is a
`DataEvents(QObject)` with a single `changed = pyqtSignal(str)` carrying a topic
string (`"accounts"`, `"transactions"`, …). Services take an `on_change` callback
wired to `events.changed.emit`. Views declare `self._topics = {...}`, set
`self._dirty = True` on a matching topic, and refresh lazily via `ensure_fresh()`
when the user navigates to them. **A service that mutates data without calling
`on_change` will leave other tabs stale.**

**Money formatting:** use `utils/formatters.py`. `fmt_money(amount, currency, compact)`
is currency-aware; `fmt_inr` is the ₹-specific shortcut. Do not hand-roll ₹ strings —
Indian digit grouping (1,23,45,678) is not what `f"{x:,}"` produces.

**Financial math lives in `utils/calculators.py`** and is pure (no DB, no side effects).
Two live caveats:

- `fv_of_sip` is an **annuity-due** (trailing `* (1 + r)`, payment at period start)
  despite a docstring saying "end-of-period". Self-consistent with
  `required_monthly_sip`, which round-trips exactly. Fix the docstring, not the math,
  unless you deliberately want ordinary-annuity semantics.
- `xirr` promises a bisection fallback that **was never implemented**. On input with
  no sign change it returns a garbage unconverged value (~2e10) instead of raising.
  Nothing calls it outside tests. Harden it before surfacing it in the UI.

**Currency aggregation is INR-only.** `account_repo.total_balance`,
`holding_repo.total_current_value`, and `liability_repo.total_outstanding` are plain
`SUM()` with no FX conversion. `AppContext.has_mixed_currencies()` exists but its
result is not used to adjust totals. All current accounts are INR, so this is latent.

**`total_balance` excludes `account_type = 'credit_card'`** to avoid double-counting
against the `liabilities` table. Note that accounts *also* carry descriptive
`loan_*`/`cc_*` fields, and the same debt can legitimately exist in both places —
only a soft UI warning prevents it (`AppContext.account_has_loan_fields`).

---

## Commands

```bat
run_setup.bat            :: create .venv, install requirements
run.bat                  :: launch the app
run_tests.bat            :: full pytest suite
run_tests.bat -m smoke   :: E2E + UI smoke only
run_smoke_tests.bat      :: same, convenience wrapper
run_build_exe.bat        :: PyInstaller build via personal_finance.spec
```

Tests need `PyQt6` + `pytest` + `pytest-qt` and the project's Windows `.venv`.
They **cannot run in a Linux sandbox** — the venv holds Windows `.exe` binaries.
When you cannot execute tests, say so explicitly rather than implying they passed.

Cheap checks that work anywhere:

```bash
python3 -m compileall -q -x '(\.venv|build|dist)' .   # syntax
grep -rn "from db\|from repositories" ui/             # layering rule
```

---

## Repo layout

```
main.py                  Entry point: bootstrap → Qt → shutdown
config/                  settings.py (paths, autosave), constants.py (enums),
                         account_fields.py (single source for account columns)
db/                      connection.py (SQLite singleton), schema.sql, migrate.py
models/                  Dataclasses, one per table, all inherit BaseModel
repositories/            One per table, all inherit BaseRepository[T]
services/                Business logic + app_context.py (DI wiring, signal bus)
ui/  main_window.py      Sidebar nav; NAV_ITEMS list drives the stack
     views/              One per nav item (8 total)
     widgets/            Reusable: KpiCard, *_tile.py
     dialogs/            Add/edit modals
     theme/badges.py     Shared badge colours
     helpers/            account_combo.py etc.
     resources/styles/theme.qss   Dark theme
utils/                   calculators, formatters, validators, logger, csv/json handlers
data/                    seed/ (ships), store/ (SOURCE OF TRUTH), reference/,
                         cache/, user/backups/, app.db (disposable)
tests/                   conftest.py fixtures + test_services/ test_repositories/
                         test_smoke/ test_utils/
docs/archive/            Superseded planning docs, kept for history
```

Key fixtures in `tests/conftest.py`: `temp_db` (schema + migrations, empty),
`empty_store` (writable store dir with `[]` files), `bootstrapped_session`
(mirrors real app bootstrap). Use these rather than hand-rolling a DB.

---

## Current state and open gaps

`STATUS.md` is the single current-state document. As of the last review:

| # | Gap | Notes |
|---|-----|-------|
| 1 | Non-atomic store writes | Highest-value fix; see above |
| 2 | Junk data in live store | Account `qwe` holds ₹50,00,000, `is_active=1`, skewing net worth and all recorded snapshots |
| 3 | No git repository | `.gitignore` exists but there is no `.git` |
| 4 | No FX layer | `fx_rates` table absent; aggregations are plain `SUM()` |
| 5 | No `stock_master` table | `data/seed/stock_master.csv` ships unused; loader block is a permanent no-op |
| 6 | No `MasterDetailView` base | 5 views duplicate the tile-list + detail-pane layout |
| 7 | No versioned migrations | Additive-only; `db/migrations/` is just a README |
| 8 | XIRR unsurfaced and unhardened | Calculator exists, no callers |
| 9 | No recurring auto-posting | SIPs/EMIs/premiums must be logged manually; only income has a pending-sources check |

Tests exist for all 12 services and all 9 repositories, but a prior pass added 15 of
those files **without ever executing them** (sandbox had no PyQt6). Treat suite-green
as unverified until `run_tests.bat` is run on Windows.

---

## Working agreements

- **Don't claim tests pass if you didn't run them.** Say which checks you actually ran.
- **Don't add a 5th planning document.** Update `STATUS.md`; archive rather than accumulate.
- **Respect the layering rule** — it's the main thing keeping this codebase pleasant.
- **New table? Touch both load and dump orders**, or data silently fails to persist.
- **Mutating service? Call `on_change(topic)`**, or other tabs go stale.
- This is real personal financial data. Prefer additive, reversible changes; when
  touching `data/store/` or the persister, take a backup first.

## Project skills

Task-specific playbooks live in `docs/skills/`. Read the relevant one before starting:

| Skill | Use when |
|-------|----------|
| `docs/skills/add-entity/` | Adding a new tracked record type (table + model + repo + service + view) |
| `docs/skills/add-view/` | Adding or editing a PyQt6 view; debugging stale tabs |
| `docs/skills/verify-changes/` | Before calling any change done |
| `docs/skills/data-hygiene/` | Numbers look wrong; after bulk edits; periodic data audit |

`docs/skills/data-hygiene/check_store.py` is runnable directly and read-only:

```bash
python docs/skills/data-hygiene/check_store.py
```

To activate these as loadable skills, copy the tree to `.claude/skills/`:

```bat
xcopy docs\skills .claude\skills\ /E /I /Y
```

They work as plain reference documentation either way.
