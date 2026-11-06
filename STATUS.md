# Status — Personal Finance Manager

**Single source of truth for the current state of this project.** Update this file in
place; don't add another planning document. Superseded plans live in `docs/archive/`.

- Architecture and conventions → `CLAUDE.md`
- Setup and usage → `README.md`
- Task playbooks → `docs/skills/`

**Last verified against the code:** 2026-07-20.

---

## Health

Architecture is sound and the codebase is in good shape. ~12k LOC across a clean
`models → repositories → services → ui` stack.

Verified this pass, not just asserted:

- Every Python file compiles (`compileall`, clean)
- **Layering rule holds** — zero `db` / `repositories` imports anywhere in `ui/`
- No `TODO` / `FIXME` / `HACK` markers in application code
- All 12 services and all 9 repositories have unit-test files
- 8 nav views, all wired through `AppContext`

Not verified: the test suite has **not been executed**. See gap #4.

---

## Open gaps

Ordered by value, not by size. Each was re-confirmed by reading the code on 2026-07-20.

### 1. Store writes are not atomic — *durability*

`DataPersister.dump_store_data` calls `out_path.write_text(...)` straight over each live
JSON file. A crash or power loss mid-write truncates that file. Autosave re-runs this
every 60s with `make_backup=False`, so the exposure is continuous.

For an app whose whole premise is "the JSON files are the source of truth for 30 years,"
this is the weakest link. Fix: write `<name>.tmp`, then `os.replace()` — atomic on both
Windows and POSIX.

### 2. Junk data in the live store — *data correctness*

Account `qwe` (id=7) holds **₹50,00,000** with `is_active=1`. Also an inactive `test1`.
The ₹50L is in every net-worth figure the app has reported and is baked into all 14
recorded `net_worth_snapshots` — deleting the account will not retroactively fix those.

Real net worth is roughly **−₹27L**, not the **+₹23L** currently displayed.

Run `python docs/skills/data-hygiene/check_store.py` to reproduce.

### 3. No version control — *risk*

A well-written `.gitignore` exists but there is no `.git` directory. 12k LOC with no
history, no diffs, no way back. `git init` is a two-minute fix and gates safe work on
everything else here.

### 4. Test suite is unverified

A prior pass added 15 test files (7 repository, 8 service) that were only `py_compile`d,
never executed — the sandbox had no PyQt6 and no network. Coverage *looks* complete but
suite-green is an assumption. Run `run_tests.bat` on Windows to establish a baseline.

### 5. `xirr` is unhardened and unused

`utils/calculators.xirr` promises a bisection fallback in its docstring that was never
implemented. On input with no sign change it returns ~2e10 rather than raising. Nothing
calls it outside tests — latent, not live, but it's the first function you'd reach for
when surfacing portfolio returns.

### 6. `fv_of_sip` docstring contradicts its math

Says "end-of-period payment"; the trailing `* (1 + r)` makes it an annuity-due
(beginning-of-period), ~1% higher. Self-consistent — `required_monthly_sip` round-trips
exactly — so this is a documentation bug, not a math bug. Worth resolving deliberately
given the 30-year projections built on it.

### 7. No FX layer

`account_repo.total_balance`, `holding_repo.total_current_value`, and
`liability_repo.total_outstanding` are plain `SUM()` with no currency conversion.
`AppContext.has_mixed_currencies()` exists but its result never adjusts totals. All 7
accounts are currently INR, so this is latent — it becomes a live correctness bug the
moment a foreign-currency account is added.

### 8. No `stock_master` table

`services/data_loader.py` guards on `_table_exists("stock_master")`, but `schema.sql`
never creates it — so that block is a permanent no-op and `data/seed/stock_master.csv`
ships unused. Market-cap classification must be entered by hand per holding.

### 9. No `MasterDetailView` base widget

`accounts`, `goals`, `investments`, `liabilities`, and `income` views each re-implement
the same tile-list + detail-pane layout and selection handling. Deferred twice as
"large refactor, low risk if deferred" — still true. If a sixth such view is ever added,
extract the base class first.

### 10. Additive-only migrations

`db/migrate.py` can add columns and nothing else. `SCHEMA_VERSION` is a hardcoded `1`
and `db/migrations/` holds only a README. No path for renames, drops, retypes, or
backfills — fine so far, thin for a schema meant to evolve over decades.

### 11. No recurring auto-posting

Only income has a recurring flag and a pending-sources check. `holdings.sip_amount`,
`holdings.premium_due_date`, `liabilities.emi_amount`, and `liabilities.next_due_date`
all exist, but nothing posts ledger transactions from them — every SIP, EMI, and premium
is logged by hand each month. This is the biggest day-to-day usability gap.

### 12. Loan double-entry is a soft warning only

`AppContext.account_has_loan_fields()` triggers a UI reminder when an account carries
loan fields, but nothing prevents or reconciles the same debt also existing as a
`liabilities` row. Currently 2 liabilities and no account loan fields set, so no live
double-count.

---

## Suggested order

1. `git init` (#3) — do this before touching anything else
2. Atomic writes (#1) — small, self-contained, removes the standing data-loss risk
3. Purge junk data (#2) — decide what to do about the contaminated snapshots
4. Run `run_tests.bat` (#4) — establish a real baseline
5. Then pick from #5–#12 by what you actually want the app to do

Items #7–#12 are deliberate deferrals rather than oversights. None needs doing before
the app is useful; each becomes worth doing when its trigger appears — a foreign-currency
account, a sixth tile view, a schema rename, a missed SIP entry.

---

## Environment note

The Linux sandbox used for analysis **cannot run this project's tests**: `.venv` is a
Windows venv holding `.exe` binaries, and there is no network access to install PyQt6 or
pytest. Static checks (`compileall`, layering greps, the store audit) work fine there;
anything requiring Qt must run on Windows via `run_tests.bat`.

Any pass that couldn't run the tests should say so explicitly rather than implying green.
