---
name: add-view
description: Build or modify a PyQt6 view in the Personal Finance Manager. Use when adding a new tab to the sidebar, editing an existing view under ui/views/, creating tiles or dialogs, or debugging why a tab shows stale data after an edit elsewhere.
---

# Building a view

Views are Qt-only. They receive an `AppContext` and call services through it. **A view
must never import from `db/` or `repositories/`** — that rule is currently unbroken and
worth keeping.

## The standard view skeleton

Five views (`accounts`, `goals`, `investments`, `liabilities`, `income`) share the same
tile-list + detail-pane shape. `liabilities_view.py` is the cleanest one to copy.

```python
class PpfView(QWidget):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self._topics = {"ppf", "accounts"}   # topics that dirty this view
        self._dirty = True
        self._svc = ctx.ppf_service
        self._items: list[Ppf] = []
        self._tiles: list[PpfTile] = []
        self._selected_id: Optional[int] = None
        self.ctx.events.changed.connect(self._on_data_changed)
        self._build()
        self.refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)
        # header (QLabel objectName="pageTitle") → KPI row → QSplitter(tiles | detail)

    def _on_data_changed(self, topic: str) -> None:
        if topic in self._topics:
            self._dirty = True

    def ensure_fresh(self) -> None:
        if self._dirty:
            self.refresh()

    def refresh(self) -> None:
        self._items = self._svc.list_active()
        self._refresh_tiles()
        self._refresh_kpis()
        self._dirty = False
```

## The refresh contract

This is the part that causes bugs.

`MainWindow._on_nav_changed` calls `ensure_fresh()` if the view has it, else `refresh()`.
So refreshing is **lazy** — a view rebuilds when the user navigates to it, not when the
data changed. The chain:

```
service mutates → on_change("topic") → events.changed.emit("topic")
    → every view's _on_data_changed → sets _dirty if topic matches
    → user navigates to that tab → ensure_fresh() → refresh()
```

Two ways to break it:

- **View lists the wrong topics.** Editing an account should dirty the Liabilities view
  too, because it renders account names. Include every topic whose data you *display*,
  not just the one you own.
- **Service forgot `on_change`.** Then nothing is ever marked dirty. If a tab is stale
  after an edit, check the service mutation path before touching the view.

Implementing `ensure_fresh` is what makes a view lazy. A view with only `refresh()`
rebuilds on every single navigation — fine for cheap views, wasteful for tile lists.

## Registering the view

Add to `NAV_ITEMS` in `ui/main_window.py`:

```python
NAV_ITEMS = [
    ("Dashboard",    DashboardView),
    ...
    ("PPF",          PpfView),
]
```

List order is sidebar order. Each entry is constructed once at startup with
`view_cls(self.ctx)` — so a slow `__init__` slows app launch for every tab, not just
this one. Keep construction light and do the work in `refresh()`.

## Styling

- Dark theme lives in `ui/resources/styles/theme.qss`, loaded once in `main.py`.
  Style via `setObjectName(...)` + a QSS rule; avoid inline stylesheets.
- Existing object names worth reusing: `pageTitle`, `sidebar`.
- Badge colours come from `ui/theme/badges.py` — import the relevant map plus
  `FALLBACK_BADGE` for unknown types. Don't hardcode hex in a view.
- Money: `fmt_money(amount, currency)` or `fmt_inr(amount)` from `utils/formatters.py`.
  Also `fmt_pct` and `fmt_date`. Never hand-roll ₹ strings — Indian digit grouping
  (1,23,45,678) is not what `f"{x:,}"` gives you.
- Account dropdowns: `ui/helpers/account_combo.py`, populated from
  `ctx.account_options_active()`.

## Dialogs

Add/edit modals live in `ui/dialogs/`. They take the values they need plus whatever
lookups they display, and return data — they don't call services directly; the view
does the save. Route validation through `utils/form_validation.py` for consistent
messages rather than ad-hoc inline checks.

## Known duplication

The five tile+detail views each re-implement the same layout, selection handling, and
tile-clearing logic. A shared `MasterDetailView` / `TileListPanel` base has been
deferred twice (it's gap #6 in `STATUS.md`). If you are adding a **sixth** such view,
that's the moment to extract the base class instead — you'd be writing the duplication
for the sixth time. Extract, then migrate the existing five one at a time.

## Verification

```bash
python3 -m compileall -q -x '(\.venv|build|dist)' .
grep -rn "from db\|from repositories" ui/     # must be empty
```

Then on Windows: `run_tests.bat -m smoke` — `tests/test_smoke/test_app_launch.py`
constructs every nav page and switches through them, so a new view registered in
`NAV_ITEMS` is covered automatically. If the view needs seeded data to render, follow
the pattern in `tests/test_smoke/test_projections_view.py`.

UI tests need PyQt6 and the Windows `.venv`; they cannot run in a Linux sandbox. If you
couldn't run them, say so rather than implying they passed.
