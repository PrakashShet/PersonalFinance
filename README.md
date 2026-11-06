# Personal Finance Manager

A modular PyQt6 desktop app for tracking accounts, income, investments, liabilities, goals, and projections.

## Data philosophy

**Source of truth lives in human-readable files** under `data/store/` (JSON). **SQLite is the in-session working database** — populated from those files at startup, queried during runtime, and dumped back on save/exit.

Why this hybrid?
- JSON files are easy to back up to Drive/Dropbox, diff with git, and inspect with any editor
- SQLite gives you fast joins, aggregations, and FK integrity for the actual UI
- If a file gets corrupted, restore from `data/user/backups/` (auto-rotated, last 10 kept)

```
boot:  data/store/*.json  ──►  SQLite (in-memory queries)
save:  SQLite             ──►  data/store/*.json  (+ timestamped backup)
```

## Project structure

```
personal_finance/
├── main.py                       # Entry point — bootstrap + UI + shutdown
├── requirements.txt
├── README.md
│
├── config/
│   ├── settings.py               # Paths, locale, autosave interval
│   └── constants.py              # Enums: AccountType, HoldingType, StockCap, etc.
│
├── db/
│   ├── connection.py             # SQLite singleton with WAL + FK enforcement
│   ├── schema.sql                # All DDL — idempotent
│   └── migrations/               # Migration notes; version tracked in schema_version
│
├── models/                       # Dataclasses (one per entity)
│   ├── base.py                   # to_dict / from_row / from_dict helpers
│   ├── account.py
│   ├── transaction.py
│   ├── holding.py                # Polymorphic — SIP/FD/stock/gold/insurance
│   ├── income.py
│   ├── liability.py
│   ├── goal.py
│   └── snapshot.py
│
├── repositories/                 # Thin SQL data-access layer
│   ├── base_repo.py              # Generic CRUD (get/list/insert/update/delete)
│   ├── account_repo.py
│   ├── transaction_repo.py
│   ├── holding_repo.py
│   └── other_repos.py            # Income, Liability, Goal repos
│
├── services/                     # Business logic — UI calls into here
│   ├── data_loader.py            # JSON/CSV → SQLite at startup
│   ├── data_persister.py         # SQLite → JSON on shutdown (+ backup)
│   ├── app_context.py            # Wires all services; injected into views
│   ├── account_service.py
│   ├── transaction_service.py
│   ├── income_service.py / income_source_service.py
│   ├── liability_service.py / goal_service.py
│   ├── investment_service.py     # Asset allocation, cap mix, maturities
│   ├── net_worth_service.py      # Balance sheet, snapshot computation
│   └── projection_service.py     # Future projections, SIP needed, retirement
│
├── ui/                           # PyQt6 — strictly view code, no SQL
│   ├── main_window.py            # Sidebar + QStackedWidget shell
│   ├── views/                    # One per nav item (Dashboard, Accounts, ...)
│   ├── widgets/                  # Reusable (KpiCard, charts, tables)
│   ├── dialogs/                  # Add/edit modals
│   └── resources/
│       ├── styles/theme.qss      # Dark theme
│       └── icons/
│
├── utils/
│   ├── logger.py                 # Rotating file + stdout
│   ├── calculators.py            # SIP, FV, EMI, XIRR
│   ├── formatters.py             # Indian numbering (1,23,45,678), ₹, %
│   ├── validators.py
│   ├── csv_handler.py
│   └── json_handler.py
│
├── data/                         # ━━━━━━━━━━━━━━━━━━━━ THE DATA DIRECTORY
│   ├── seed/                     # Ships with app (don't edit at runtime)
│   │   ├── categories.json       # Default income/expense categories
│   │   └── stock_master.csv      # Symbol → market cap mapping
│   ├── store/                    # The user's actual data (source of truth)
│   │   ├── accounts.json
│   │   ├── transactions.json
│   │   ├── holdings.json
│   │   ├── income_sources.json
│   │   ├── liabilities.json
│   │   ├── goals.json
│   │   ├── goal_holdings.json
│   │   ├── holding_valuations.json
│   │   ├── net_worth_snapshots.json
│   │   └── reminders.json
│   ├── reference/                # Static reference data
│   │   ├── tax_slabs.json
│   │   └── assumptions.json
│   ├── cache/                    # NAVs, prices (auto-refreshed)
│   ├── user/backups/             # Auto-rotated backups (last 10)
│   └── app.db                    # Generated; safe to delete
│
├── logs/
│   └── app.log
│
└── tests/
    ├── conftest.py               # Shared DB/store fixtures
    ├── test_services/            # Service unit tests
    ├── test_smoke/               # E2E + UI launch smoke tests
    ├── test_repositories/        # Repository CRUD smoke tests
    └── test_utils/
```

## Module responsibilities (the import direction)

```
   ui  ──►  services  ──►  repositories  ──►  db
                    └─►  models             ▲
                                            │
                       data_loader/persister┘  (reads/writes data/*.json)
```

Strict rule: **UI never imports from `repositories` or `db` directly.** Always go through a service. This keeps the UI testable and the business logic centralized.

## Setup

**Windows:**

```bat
setup.bat
run.bat
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

**Run tests:**

```bat
run_tests.bat
```

**Project documentation:**

| File | What it's for |
|------|---------------|
| `CLAUDE.md` | Architecture, conventions, and gotchas — read this before changing code |
| `STATUS.md` | Current state and the open-gap list |
| `docs/skills/` | Task playbooks (add an entity, add a view, verify changes, audit data) |
| `docs/archive/` | Superseded planning docs, kept for history only |

On first run:
1. `bootstrap()` connects to SQLite (creates `data/app.db`)
2. Applies `db/schema.sql`
3. Loads seed data (categories, stock master)
4. Loads user store (the sample data ships with realistic example records)
5. Loads reference data (tax slabs, assumptions)
6. Launches the PyQt6 main window

On graceful exit:
1. Creates a timestamped backup in `data/user/backups/`
2. Dumps every table back to its JSON file under `data/store/`
3. Closes the SQLite connection

## What's working out of the box

- Full schema for accounts, transactions, holdings (all investment types you listed), liabilities, goals, snapshots, reminders
- Dashboard with live KPIs (net worth, assets, liabilities, portfolio value, cash, invested)
- Asset allocation breakdown (equity / debt / gold / alt / insurance)
- Stock breakdown by market cap (SME / small / mid / large)
- Net worth calculation and snapshot persistence
- Projection engine (SIP needed, retirement corpus, future value)
- Indian-locale formatting (₹, lakhs, crores)
- CSV/JSON round-trip with backup rotation

## Adding a new entity (the playbook)

Say you want to add **PPF accounts** as a first-class entity (instead of treating them as a holding):

1. Add CREATE TABLE block to `db/schema.sql`
2. Create `models/ppf.py` (dataclass mirroring the table)
3. Create `repositories/ppf_repo.py` (subclass `BaseRepository`)
4. Create `services/ppf_service.py` (interest calculation, deposit limits)
5. Add `("ppf.json", "ppf")` to `STORE_LOAD_ORDER` in `data_loader.py` and `STORE_DUMP_ORDER` in `data_persister.py`
6. Create `data/store/ppf.json` with `[]`
7. Create `ui/views/ppf_view.py` and register it in `main_window.py`

The pattern repeats for every entity.

## Backups

Every shutdown auto-creates `data/user/backups/YYYYMMDD_HHMMSS/` with copies of all JSON store files. The latest **30** snapshots are kept (`MAX_BACKUPS` in `data_persister.py`). Autosave every 60s updates `data/store/` without creating a backup. To restore: copy any backup folder's contents over `data/store/` and relaunch.

## Roadmap (suggested build order)

1. **Phase 1 (MVP):** Accounts + Transactions + manual Investments + Dashboard
2. **Phase 2:** Auto NAV/price fetch (cache/), holding valuations, goals
3. **Phase 3:** Tax module, reminders, CSV import (Zerodha/Groww/bank statements)
4. **Phase 4:** Document vault, encrypted backups, PDF reports
