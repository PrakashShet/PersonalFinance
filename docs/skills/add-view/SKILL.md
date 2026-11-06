---
name: add-view
description: Build or modify a PyQt6 page in the Personal Finance Manager. Use when adding a sidebar page, editing anything under ui/views/, creating widgets or dialogs, theming (light/dark), or debugging why a page shows stale data after an edit elsewhere.
---

# Building a page

Pages are Qt-only. They receive an `AppContext` and call services through it. **A page
must never import from `db/` or `repositories/`.**

## List pages: subclass `MasterDetailView`

Accounts, Budgets, Income, Investments, Liabilities and Goals are all
`ui/views/master_detail.MasterDetailView`: header → KPI row → optional extra row
(`build_extra`, e.g. banners) → filters → tile list | detail. A new list page is
mostly data (`ui/views/budgets_view.py` is the newest complete example):

```python
class PpfView(MasterDetailView):
    title = "PPF"
    subtitle = "Public Provident Fund accounts."
    add_label = "Add PPF account"
    topics = frozenset({"ppf", "accounts"})      # every topic whose data you DISPLAY
    inactive_label = "Show closed"               # None hides the toggle
    empty_icon, empty_title, empty_text = "investments", "No PPF yet", "Add one to track it."

    def build_kpis(self):
        self.k_total = KpiCard("Total balance", icon_name="coins")
        return [self.k_total]

    def fetch(self, include_inactive):
        return self.ctx.ppf_service.list_all(include_inactive)

    def refresh_kpis(self, items):
        self.k_total.set_value(fmt_inr(sum(p.balance for p in items), compact=True))

    def make_tile(self, p, selected):
        return ListTile(p.id, p.name, p.institution or "", value=fmt_inr(p.balance),
                        icon_name="investments", muted=not p.is_active, selected=selected)

    def render_detail(self, p, panel):
        panel.set_header(p.name, p.institution or "")
        panel.set_actions([("Edit", self._edit, "primary", "edit")])
        panel.add_stats("Balance", [("Balance", fmt_inr(p.balance)),
                                    ("Matures", fmt_date(p.maturity_date))])

    def on_add(self): ...
```

Other pages (Dashboard, Transactions, Projections, Settings) are plain `QWidget`s built
from the same blocks; copy the closest one.

## Register it

`NAV` in `ui/main_window.py` - `(key, label, icon_name, cls)`. List order is sidebar order
and the shortcut (`nav_shortcut`: Ctrl+1 … Ctrl+9, then Ctrl+0 for the tenth page).
There are ten pages now; an eleventh would have no shortcut, and a smoke test says
so - group pages before adding one. Add the page to the sidebar's **New** menu
(`MainWindow._new_menu`) if it creates something. Every page is constructed once at
startup, so keep `__init__` light and do the work in `refresh()`.

Cross-page links: `navigation.go("budgets", budget_id=3)` calls the target's
`show_with(**kwargs)`. Accept and ignore unknown keywords (`**_kw`).

Wording shared by several pages (a status phrase, a hint) goes in `ui/helpers/`
(e.g. `budget_text.py`), so it reads the same everywhere.

## Building blocks (`ui/widgets/`)

`Card`, `PageHeader`, `KpiCard`, `Badge`, `Banner`, `EmptyState`, `SegmentedControl`,
`StatGrid`, `ActivityRow`, `ElidedLabel`, `ListTile`, `DetailPanel`, `TrendChart`,
`SegmentedBar`, `button(text, kind, icon_name, on_click)`, `progress(pct, tone)`.

- **Long single-line text (names, notes) must be `ElidedLabel`.** A plain `QLabel`'s
  minimum width is its full text, which pushes the whole page off-screen.
- Every page has an empty state that says what to do next (`EmptyState(..., action)`).
- Actions sit next to what they act on (`DetailPanel.set_actions`), primary first.

## Theming - no colours in Python

- Colours are tokens in `ui/theme/tokens.py` (LIGHT and DARK must have the same keys).
- Style through object names and properties in `ui/resources/styles/theme.qss`:
  `label(text, "rowMeta")`, `set_tone(widget, "positive")`, `button(..., kind="danger")`.
- Painting or table item colours: `theme.qcolor("positive")` at refresh/paint time, and
  connect `theme.changed` if the widget paints itself. Pages are marked dirty and the
  visible one refreshed on a theme switch, so table colours follow automatically.
- New token? Add it to **both** dicts; the smoke test fails if the stylesheet keeps a `$`.
- **Tones on role labels.** A rule like `QLabel#statValue { color: ... }` outranks a bare
  `QLabel[tone="negative"]`, so a role that takes a tone must be listed in the tone block
  of `theme.qss` (`QLabel#<role>[tone="..."]`). Without it the tone silently never shows -
  `test_tones_show_on_role_labels` guards the existing roles; add yours there too.
- Segmented controls size every segment for the semi-bold checked state; long labels are fine.
- Charts: categorical colours `series_1..5` by entity in a fixed order, never by rank;
  always a legend or table with names and values (see `ui/widgets/charts.py`).
- Icons: add a 24×24 stroke path to `ui/theme/icons.py`. No image files.

## The refresh contract

```
service mutates → on_change("topic") → events.changed
    → every page's _on_data_changed sets _dirty if topic in _topics
    → the VISIBLE page refreshes ~60 ms later (MainWindow._live)
    → other pages refresh when opened (ensure_fresh)
```

Two ways to break it: the page lists the wrong `topics` (include every topic whose data
you show, not just the one you own), or the service forgot `on_change` (then nothing is
dirty *and* the save-after-change never fires).

## Dialogs

Add/edit modals live in `ui/dialogs/`. They take the values and lookups they display and
return data - the page saves. Call `style_button_box(box)` so Save is the primary
button. Small single-purpose prompts belong in `ui/dialogs/quick_dialogs.py`.

- **Never refuse Save silently.** Show `QMessageBox.warning(self, "Please check", ...)`
  naming what's missing, then focus the field.
- **Edit + Save without changes must leave the record identical** -
  `test_e2e_edit_fidelity` checks every dialog. A date the record may not have is a
  `DateField` (`ui/widgets/date_field.py`: shows *Not set*, `iso()` returns `None`);
  a field hidden for this record's type keeps its stored value; a combo whose value can
  be unset needs a *Not set* item.
- Money inputs use the `₹ ` prefix; previews and labels use `fmt_inr`, never
  `f"{x:,}"` (Western grouping).

## No flicker

- Never `show()` / `setVisible(True)` a widget that has no parent yet - on Windows it
  opens as its own window for a moment. Create children with a parent, or only ever
  `hide()` them during construction; a child shows with its parent anyway.
- Remove widgets with `discard(w)` or `clear_layout(layout)` from `ui/widgets/common.py`.
  They hide before detaching: a widget added to a visible container has a "show" queued
  for the next event pass, and if it is detached first it pops up as a window.
- `test_no_widget_flashes_up_as_a_window_of_its_own` visits every page, selects every item
  and opens every form, and fails on any stray window.

## Big tables

Filling a `QTableWidget` row by row while its columns *resize to contents* re-fits the
columns after every cell - rows x rows work that froze the app for minutes with a few
years of history. Turn updates off and set the header to `Fixed` while filling, then
restore the modes once (see `TransactionsView.refresh` / `_fit_columns`).

## Verify

```bash
python -m compileall -q -x '(\.venv|build|dist)' .
grep -rn "from db\|from repositories" ui/          # must be empty
grep -rnE "#[0-9a-fA-F]{6}" ui/views ui/widgets ui/dialogs --include=*.py   # must be empty
run_tests.bat -m smoke                             # builds, switches and re-themes every page
python tools/render_pages.py --out shots           # LOOK at both themes before calling it done
```

`render_pages.py` works on a temporary copy of the store, so it is always safe - but its
images show real data: look at them, never commit them. If users will see the change,
regenerate the user guide's images from demo data (`python tools/make_user_guide.py`, see
the **user-guide** skill) and update its text.
