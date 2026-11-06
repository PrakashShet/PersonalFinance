---
name: verify-changes
description: Verification checklist before calling work on the Personal Finance Manager done. Use after editing any Python in this repo, before reporting a task complete, or when deciding whether a change is safe to trust. Covers syntax, the layering rule, persistence wiring, tests, a look at the UI, financial math and honest reporting of what could not be run.
---

# Verifying a change

The rule that matters most: **report what you actually ran.** An earlier pass
added 15 test files, never ran them, and left the docs implying the suite passed.
Don't repeat that.

## Tier 1 - always, works anywhere

```bash
python -m compileall -q -x '(\.venv|build|dist)' .                    # every file parses (silent = OK)
grep -rn "from db\|from repositories" ui/                              # must print nothing
grep -rnE "#[0-9a-fA-F]{6}" ui/views ui/widgets ui/dialogs ui/helpers --include=*.py   # no colours in Python
grep -rn "print(\|breakpoint()\|import pdb" --include=*.py services/ ui/ db/ repositories/ utils/ models/ config/
```

If a view needs data, add a service method or an `AppContext` helper. A view
never imports a repository.

## Tier 2 - when you touched persistence

SQLite runs in memory and is rebuilt from `db/schema.sql` and the JSON store at
every launch, so a schema change never needs an SQLite migration. What it does
need:

- **New table:** an entry in both `STORE_LOAD_ORDER` (`services/data_loader.py`,
  `(filename, table)`) and `STORE_DUMP_ORDER` (`services/data_persister.py`,
  `(table, filename)` - note the order is reversed), each placed after the tables
  it references. Add it to `STORE_FILES`, and its foreign keys to `LINKS`, in
  `docs/skills/data-hygiene/check_store.py`.

  ```bash
  grep -n "<table>" services/data_loader.py services/data_persister.py docs/skills/data-hygiene/check_store.py
  ```

- **New column:** `db/schema.sql` only. A `NOT NULL` column needs a `DEFAULT`,
  because existing records won't have the key.
- **Changed meaning** (a rename, retype or backfill): a store migration in
  `services/store_migrations.py`, which bumps `STORE_VERSION` and runs once
  after a backup.
- Don't create files in the live `data/store/`. The loader creates a missing
  file as `[]` on the next start.

## Tier 3 - the test suite (Windows `.venv`)

```bat
run_tests.bat              :: everything - 147 tests, about 10 s, as of 1.1.0
run_tests.bat -m smoke     :: E2E + UI only
```

`tests/conftest.py` points `PFM_HOME` at a temporary folder, so tests never touch
real data. Use the fixtures: `temp_db` (empty schema), `empty_store`,
`bootstrapped_session`, and `isolated_app_db` in the smoke tests. A smoke test
that emits `theme.changed` needs `isolated_app_db`, because windows left over
from earlier tests are still listening.

The suite needs PyQt6, pytest and pytest-qt from the project's `.venv`. Where
that can't run (a Linux sandbox, for example), say so plainly:

> Ran compileall and the layering check, both clean. Could not run pytest:
> PyQt6 isn't installable here. Please run `run_tests.bat`.

Not "tests should pass".

## Tier 4 - round trip and a look, for anything touching data or UI

Work on a **copy**. Never test against the live `data/store/`, which holds real
financial data.

1. Copy the store into a scratch `PFM_HOME`, or build the demo:
   `python tools/make_demo_store.py <new folder>`.
2. `run.bat` with `PFM_HOME` set, make the change through the UI, then quit.
3. Confirm the change landed in `<PFM_HOME>/data/store/*.json`, then relaunch and
   confirm it is still there. This catches a missing load-order entry.
4. `python docs/skills/data-hygiene/check_store.py --store <PFM_HOME>/data/store`
   must report no new findings (it checks the ledger invariant).
5. UI changes: `python tools/render_pages.py --store <copy> --out shots`, then
   **look** at both themes. If users will see the change, also run the
   **user-guide** skill.

If you touched a service mutation, check the refresh chain too: change a record
on one page, open another page that shows it, and confirm it updated
(`service → on_change(topic) → events.changed → page._dirty → ensure_fresh()`).

## Financial math

Changes to `utils/calculators.py` and other money logic need numbers worked out by
hand, not just a passing test. Tests written against the current implementation
will happily confirm a wrong formula.

- `fv_of_sip` is an annuity-due (contributions at the start of each period), and
  `required_monthly_sip` is its exact inverse. Change both or neither.
- `xirr` raises `ValueError` when no rate exists. Callers show nothing (`None`)
  rather than a made-up figure.

Sanity values:

```python
emi(3820000, 0.085, 240)        # ≈ 33150.85
fv_of_sip(10000, 0.12, 10)      # ≈ 2323390.76  (annuity-due)
xirr([(0, -100), (365, 110)])   # ≈ 0.10
```

## Before reporting done

- [ ] `compileall` clean; no `db`/`repositories` imports in `ui/`; no hex colours in Python
- [ ] Persistence wired in the loader, the persister and `check_store.py` (if a table changed)
- [ ] `check_store.py` shows no new findings on a copy
- [ ] Tests run, with the count reported - or explicitly not run, with the reason
- [ ] Screens looked at in both themes (if the UI changed); user guide updated if users see it
- [ ] `STATUS.md` updated if this closed or opened a gap; no new planning document
- [ ] Before any push: `python tools/privacy_scan.py --history` (see the **release** skill)
