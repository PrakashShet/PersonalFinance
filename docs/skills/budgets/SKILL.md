---
name: budgets
description: Work on spending limits (budgets) in the Personal Finance Manager - what counts as spending, monthly / yearly periods (calendar or financial year), near / over states, the expense-dialog hint, dashboard alerts, the audit and the demo data. Use when changing budget behaviour, adding a period type or rollover, or when a budget figure looks wrong.
---

# Budgets

A budget is a spending limit for one **expense category**, per **month** or per
**year**. Users set it on the Budgets page; it also shows up while they type an
expense, on the Dashboard, and in the data audit.

## The rules, and the one place each lives

| Rule | Where |
|------|-------|
| Spending = `expense` transactions in the budget's category with `start <= txn_date < end + 1 day`. Transfers, investments and adjustments never count | `TransactionRepository.expense_totals` |
| Non-INR spending is converted with `fx_rates`; without a rate it goes to `unconverted` and is **never** summed as rupees (same rule as net worth) | `BudgetService._month_totals` / `_rupees` |
| A month is a calendar month; a year starts in the month held by the `budget_year_start` preference (1 = January, 4 = April, the Indian FY) | `period_bounds`, `period_label` (pure functions) |
| Over = spent > limit by more than a paisa. Near = from 80 % (`NEAR_PCT`). Exactly at the limit is *near*, not over | `budget_state` |
| At most one limit per category and period | `UNIQUE (category_id, period)` in `db/schema.sql`; `set_limit` replaces |
| Only expense categories can have a limit | `BudgetService._validate` |
| Editing an expense never counts it twice in the hint | `impact(..., exclude_txn_id=)` |
| Wording ("₹750 left", "this financial year", the hint text) | `ui/helpers/budget_text.py` - shared by the page, the Dashboard and the dialog |

Matching is on the transaction's own category; categories have no hierarchy in
the app (`parent_id` is unused).

## Files

- Data: `budgets` in `db/schema.sql`, `models/budget.py`, `repositories/budget_repo.py`,
  `data/store/budgets.json` (last in `STORE_LOAD_ORDER` / `STORE_DUMP_ORDER`).
- Logic: `services/budget_service.py` (statuses, history, alerts, impact,
  unbudgeted, suggestion, totals). Wired in `AppContext.create` with the
  preferences object.
- UI: `ui/views/budgets_view.py` (a `MasterDetailView`), `ui/dialogs/budget_dialog.py`,
  the hint in `ui/dialogs/transaction_dialog.py` (fed by `TransactionsView._budget_hint`),
  the alert rows in `ui/views/dashboard_view.py`, the year-start choice in
  `ui/views/settings_view.py`.
- Audit: `check_budgets` in `docs/skills/data-hygiene/check_store.py`.
- Demo and guide: `tools/make_demo_store.py` (one budget over, one near, spending
  without a limit) and section 6 of `docs/user-guide/README.md`.

## Things that are easy to get wrong

- **The limit has no history.** Past periods are compared with *today's* limit.
  Storing limit changes would change what a record means: add a store migration
  (`services/store_migrations.py`) if existing `budgets.json` rows must be rewritten.
  A new optional column with a default needs none.
- **The year start is a preference** (`data/user/preferences.json`), not store
  data. Losing it only moves yearly budgets back to calendar years.
- **Changes must announce themselves.** Every mutation calls `_changed()` (topic
  `budgets`); the Budgets page, Dashboard and Settings listen for it, and it is
  what triggers the save.
- **Amounts are whole rupees in the UI** (`money()` = `fmt_inr(decimals=0)`). Don't
  use compact figures for totals that are meant to add up.

## Adding a period type (e.g. weekly or quarterly)

Update together: `PERIODS`, `period_bounds`, `period_label`, the history step in
`BudgetService.history`, `PERIOD_OPTIONS` / `PERIOD_NAMES` / `period_phrase` in
`ui/helpers/budget_text.py`, the dialog's period hint, and the allowed periods in
`check_budgets`. Existing rows stay valid, so no store migration is needed.

## Verify

```bat
run_tests.bat                    :: tests\test_services\test_budget_service.py has hand-worked numbers
python tools\make_demo_store.py %TEMP%\pfm-demo-1
set PFM_HOME=%TEMP%\pfm-demo-1 && run.bat
python tools\make_user_guide.py  :: if the page or a dialog changed - then look at the images
```

New behaviour gets a test with numbers worked out by hand in the comments, not
read back from the code.
