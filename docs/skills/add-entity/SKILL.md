---
name: add-entity
description: Add a new first-class entity (table + model + repo + service + view) to the Personal Finance Manager. Use when adding something like PPF accounts, insurance policies, rental properties, or any new tracked record type that needs its own table and tab. Also use when reviewing whether an existing entity was wired up completely.
---

# Adding a first-class entity

Worked example: adding **PPF accounts** as their own entity rather than a `holding`.
The newest real one, wired end to end, is **budgets** (table, model, repo, service,
page, dialog, audit check, demo data, user guide) - see the **budgets** skill for the
file list.

**Decide first: does this need to be an entity at all?** `holdings` is deliberately
polymorphic (SIP, FD, stock, gold, insurance, bonds, NPS…). If the new thing is just
another instrument with a value and a maturity date, add a `HoldingType` enum member
in `config/constants.py` and stop — that is minutes of work instead of hours. Create a
new entity only when it needs fields, relationships, or business rules that would
pollute `holdings`.

## The order matters

Steps 5 and 6 are the ones people forget, and skipping them means the app looks like
it works until restart, then silently loses every record.

### 1. Schema — `db/schema.sql`

Add a `CREATE TABLE IF NOT EXISTS` block. Copy the conventions verbatim from an
existing table (`liabilities` is a good short one):

```sql
id              INTEGER PRIMARY KEY AUTOINCREMENT,
name            TEXT NOT NULL,
-- ... entity columns; REAL for money, TEXT for ISO YYYY-MM-DD dates
is_active       INTEGER NOT NULL DEFAULT 1,
created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE SET NULL
```

Note `NOT NULL DEFAULT 1` on `is_active` — aggregations filter on `is_active = 1`, and
a NULL would silently exclude the row. Add `updated_at TEXT DEFAULT CURRENT_TIMESTAMP`
if the entity is edited in place (not every table has it).

Foreign keys use `ON DELETE CASCADE` for owned rows and `ON DELETE SET NULL` for
optional links. FK enforcement is on, so a bad reference raises at insert.

No SQLite migration is ever needed: the database is rebuilt in memory from
`schema.sql` on every launch, so a new table or column simply exists. (A new
`NOT NULL` column needs a `DEFAULT`, because existing records won't have the key.)

### 2. Model — `models/ppf.py`

```python
from dataclasses import dataclass
from typing import Optional
from models.base import BaseModel

@dataclass
class Ppf(BaseModel):
    id: Optional[int] = None
    name: str = ""
    # ... every column, in schema order
    is_active: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
```

Every field needs a default (dataclass ordering), and field names must match column
names exactly — `from_row` filters on `dataclass.fields`, so a typo means the value is
silently dropped, not an error.

### 3. Repository — `repositories/ppf_repo.py`

```python
from models.ppf import Ppf
from repositories.base_repo import BaseRepository

class PpfRepository(BaseRepository[Ppf]):
    table_name = "ppf"
    model_class = Ppf

    def list_active(self) -> list[Ppf]:
        return self.list_all("is_active = 1")
```

Inherited free: `get_by_id`, `list_all`, `count`, `insert`, `update`, `delete`,
`bulk_insert`. Add only aggregates and entity-specific queries. Keep SQL here.

Watch the base-class asymmetry: `insert()` drops `None` values so DB defaults apply,
but `update()` writes them as explicit `NULL`.

### 4. Service — `services/ppf_service.py`

Business logic: interest accrual, deposit limits, maturity rules. Takes the repo in
its constructor plus an `on_change` callback:

```python
class PpfService:
    def __init__(self, repo: PpfRepository, on_change=None) -> None:
        self.repo = repo
        self._on_change = on_change

    def _changed(self) -> None:
        if self._on_change:
            self._on_change("ppf")
```

**Call `self._changed()` after every mutation.** Skip it and other tabs render stale
data until restart. No Qt imports in services.

### 5. Persistence wiring — BOTH files

- `services/data_loader.py` → add `("ppf.json", "ppf")` to `STORE_LOAD_ORDER`
- `services/data_persister.py` → add `("ppf", "ppf.json")` to `STORE_DUMP_ORDER`

The **tuple order is reversed** between the two (loader is `(filename, table)`,
persister is `(table, filename)`). Getting it backwards fails loudly at boot, which is
the good outcome.

Position both entries so foreign keys resolve: a table must appear *after* everything
it references. `ppf` referencing `accounts` goes after `accounts`.

**Miss the loader entry** → data never loads back after restart.
**Miss the persister entry** → data never reaches disk; lost on quit. Silent both ways.

### 6. Store file and audit

Don't create `data/store/ppf.json` yourself - the live store is real data, and the
loader creates a missing file as `[]` on the next start (the tests' `empty_store`
fixture follows `STORE_LOAD_ORDER` automatically).

Do teach the audit about it: add `"ppf.json"` to `STORE_FILES` in
`docs/skills/data-hygiene/check_store.py`, its foreign keys to `LINKS`, and a check for
any value that would stop the app from starting or be silently ignored.

### 7. Wire into `AppContext` — `services/app_context.py`

- Instantiate the repo inside `create()`
- Add `ppf_service: PpfService` as a dataclass field
- Pass `on_change=on_change` when constructing it
- Add an `AppContext` helper if views need related lookups (e.g. `ppf_options_active()`),
  so views never reach for a repository

### 8. View — `ui/views/ppf_view.py` + register it

See the **add-view** skill for the full view pattern. Register in
`ui/main_window.py::NAV`; position in that list is the sidebar order (ten pages at
most - Ctrl+1 … Ctrl+0). Add it to the sidebar's **New** menu too.

### 9. Demo data and the user guide

Give the demo household some of the new records (`build()` in
`tools/make_demo_store.py`), regenerate the guide's screenshots
(`python tools/make_user_guide.py`) and add a section to `docs/user-guide/README.md`.
See the **user-guide** skill.

## Verification

```bash
python3 -m compileall -q -x '(\.venv|build|dist)' .
grep -rn "from db\|from repositories" ui/                          # must be empty
grep -n "ppf" services/data_loader.py services/data_persister.py docs/skills/data-hygiene/check_store.py   # all three must hit
```

Then the round-trip that actually proves it - on a **copy** of the data (`PFM_HOME`
pointing at a scratch folder):

1. `run.bat`, add one record through the UI, quit
2. Confirm the record is in `<PFM_HOME>/data/store/ppf.json`
3. Relaunch (SQLite is rebuilt in memory from the files) and confirm it is still shown

That sequence is the only real proof steps 5 and 6 are correct. Add cases to
`tests/test_repositories/` and `tests/test_services/` using the `temp_db` and
`bootstrapped_session` fixtures, and a load/save case in `tests/test_services/test_storage.py`.

**Changing an existing entity's fields or meaning** (rename, retype, backfill)? That is a
store migration: bump `STORE_VERSION` and add a step in `services/store_migrations.py`
(it runs once, after a backup, and is written back only if it loads). A brand-new
column with a default needs no migration - old records simply lack the key.

## Finally

Update the gap table in `STATUS.md` if this closes a known gap, and add a line to
`CHANGELOG.md`. Don't create a new planning document.
