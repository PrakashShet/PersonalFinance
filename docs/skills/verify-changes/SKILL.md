---
name: verify-changes
description: Verification checklist before calling work on the Personal Finance Manager done. Use after editing any Python in this repo, before reporting a task complete, or when deciding whether a change is safe to trust. Covers syntax, the layering rule, persistence wiring, tests, and honest reporting of what could not be run.
---

# Verifying a change

The rule that matters most: **report what you actually ran.** A prior pass added 15
test files, never executed them, and left the docs implying a green suite. Don't repeat
that.

## Tier 1 — always, works anywhere

```bash
# Every file still parses
python3 -m compileall -q -x '(\.venv|build|dist)' .

# The layering rule: ui must never touch db or repositories
grep -rn "from db\|from repositories" ui/          # must print nothing

# No debug leftovers
grep -rn "print(\|breakpoint()\|import pdb" --include=*.py \
     services/ ui/ db/ repositories/ utils/ models/ config/
```

`compileall` is silent on success. The `grep` for `ui/` must return zero lines — if a
view needs data, add a service method or an `AppContext` helper instead.

## Tier 2 — when you touched persistence

Any new table or column means checking both directions, because failure here is silent
until the next restart:

```bash
grep -n "<table>" services/data_loader.py services/data_persister.py   # both must hit
```

`STORE_LOAD_ORDER` is `(filename, table)`; `STORE_DUMP_ORDER` is `(table, filename)` —
reversed. Both must respect FK order.

New column on an existing table? It must be in **both** `db/schema.sql` (for fresh DBs)
and `db/migrate.py::_additions()` (for existing ones). Schema alone leaves every current
database without the column.

Then verify the data actually survives a restart:

```bash
python docs/skills/data-hygiene/check_store.py    # orphans, junk, silent zeros
```

## Tier 3 — the real test suite (Windows only)

```bat
run_tests.bat              :: everything
run_tests.bat -m smoke     :: E2E + UI launch only
```

Needs PyQt6, pytest, pytest-qt and the project's `.venv`. **These cannot run in a Linux
sandbox** — the venv holds Windows `.exe` binaries and there's no network to install
PyQt6. When blocked, say so plainly:

> Ran compileall and the layering check, both clean. Could not run pytest —
> PyQt6 isn't installable in this environment. Please run `run_tests.bat`.

Not "tests should pass."

Use the fixtures in `tests/conftest.py` rather than building a DB by hand: `temp_db`
(schema + migrations, empty), `empty_store` (writable store of `[]` files),
`bootstrapped_session` (mirrors real app bootstrap).

## Tier 4 — manual round-trip, for anything touching data

The only proof that persistence works end to end:

1. `run.bat`, make the change through the UI, quit cleanly
2. Confirm it landed in the right `data/store/*.json`
3. Delete `data/app.db`, relaunch, confirm it is still there

Step 3 is the one that catches a missing `STORE_LOAD_ORDER` entry.

If you touched a **service mutation**, also check cross-tab refresh: edit a record in
one tab, navigate to another tab that displays it, confirm it updated. The chain is
`service → on_change(topic) → events.changed → view._dirty → ensure_fresh()`. A service
that mutates without calling `on_change` leaves other tabs stale.

## Financial math

Changes to `utils/calculators.py` need a hand-checked number, not just a green test —
the tests were written against the current implementation and will happily confirm a
wrong formula. Two known traps:

- `fv_of_sip` is an **annuity-due** (trailing `* (1 + r)`) despite its docstring saying
  "end-of-period". `required_monthly_sip` round-trips with it exactly. If you "fix" one,
  fix both or you break the round-trip.
- `xirr` has no convergence guard: on input with no sign change it returns ~2e10 rather
  than raising. Harden it before any caller relies on it.

Sanity values to check against:

```python
emi(3820000, 0.085, 240)        # ≈ 33150.85
fv_of_sip(10000, 0.12, 10)      # ≈ 2323390.76  (annuity-due)
xirr([(0, -100), (365, 110)])   # ≈ 0.10
```

## Before reporting done

- [ ] `compileall` clean
- [ ] `ui/` imports no `db` / `repositories`
- [ ] Persistence wired in both loader and persister (if a table changed)
- [ ] Schema **and** `migrate.py` updated (if a column changed)
- [ ] `check_store.py` shows no new findings
- [ ] Tests run — or explicitly reported as not run, with the reason
- [ ] `STATUS.md` gap table updated if this closed or opened a gap
- [ ] No new planning document created
