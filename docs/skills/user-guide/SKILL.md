---
name: user-guide
description: Keep the user guide (docs/user-guide/README.md) and its screenshots current for the Personal Finance Manager. Use after any visible UI change, when adding a page, dialog or feature users should know about, or when screenshots look out of date. Screenshots always come from the fictional demo household, never from real data.
---

# The user guide

`docs/user-guide/README.md` is written for **people using the app**, not
developers: what each page is for, how to do the common things, and what to do
when something looks wrong. Its images live in `docs/user-guide/images/`.

## Screenshots come from demo data only

```bat
.venv\Scripts\python tools\make_user_guide.py
```

This builds the fictional household (`tools/make_demo_store.py`) in a throwaway
folder, opens the real app off-screen and writes:

| File | What |
|------|------|
| `NN-<page>.png` | every page, in sidebar (`NAV`) order, light theme |
| `dialog-*.png` | add expense (with the budget hint), add budget (with the suggestion), update balance, log payment |
| `dark-NN-<page>.png` | Dashboard and Budgets in the dark theme |

The Settings page shows a placeholder data path (`C:\Users\you\...`) so nobody's
Windows user name ends up in an image.

**Never** make guide images from the real store: `tools/privacy_scan.py` cannot
read images, so a screenshot of real data would be published unnoticed.
(`tools/render_pages.py` renders a copy of the real store - for your own review
only. Its output folder `shots/` is git-ignored.)

## After a UI change

1. Run `tools\make_user_guide.py`.
2. Open every image that changed (`git status docs/user-guide/images`). Check
   for clipped text, both themes readable, and plausible numbers.
3. Update the text: new buttons, renamed labels, changed behaviour. Name
   buttons and labels **in bold, exactly as the app shows them**.
4. A new page: once it is in `NAV`, the tool screenshots it automatically. Add a
   section and a contents entry, and update image numbers if the order changed.
5. A new dialog worth showing: add it to the dialog block in
   `tools/make_user_guide.py`.

## When the demo household needs to change

- `build(ctx, today)` in `tools/make_demo_store.py` uses the app's own services,
  so the demo follows every rule (balances equal transactions, recurring tags,
  budgets). Dates are relative to today, and nothing is dated in the future.
- It is designed to show each feature: a budget over its limit and one near it,
  spending with no limit, a due EMI, SIP and premium, unrecorded income, an FD
  about to mature, and goals linked to investments.
- Keep it fictional: invented employers and places, masked account numbers
  (`XXXX4821`), no real people.
- After changing it:

  ```bat
  python tools\make_demo_store.py %TEMP%\pfm-demo-2
  python docs\skills\data-hygiene\check_store.py --store %TEMP%\pfm-demo-2\data\store
  ```

  The audit must report *No issues found*.

## Style

- Second person, short sentences, one idea per bullet.
- Say *why* when a rule would surprise someone: adjustments aren't income, term
  insurance isn't an investment, yearly limits can follow the financial year.
- Put each screenshot right after the paragraph that introduces it, and give
  every image alt text.
- Use rupees and Indian grouping (₹1,50,000) in examples.
