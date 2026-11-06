# Project skills

Task playbooks for this repo. Each folder holds a `SKILL.md` with YAML frontmatter,
so they work both as plain documentation and as loadable skills.

| Skill | Use when |
|-------|----------|
| [`add-entity`](add-entity/SKILL.md) | Adding a new tracked record type - the ordered path from `schema.sql` to a registered page, including the persistence wiring that fails silently if missed |
| [`add-view`](add-view/SKILL.md) | Adding or editing a PyQt6 page - dependency injection, the lazy refresh contract, theming and tones, and why a page shows stale data |
| [`budgets`](budgets/SKILL.md) | Changing how spending limits work - what counts, periods, near / over, the expense-dialog hint - or a budget figure looks wrong |
| [`verify-changes`](verify-changes/SKILL.md) | Before calling any change done - tiered checks, what runs in a sandbox vs. what needs Windows, and honest reporting |
| [`data-hygiene`](data-hygiene/SKILL.md) | Numbers look wrong, after bulk edits, or as a periodic audit of `data/store/` |
| [`user-guide`](user-guide/SKILL.md) | After a visible UI change - regenerate the guide's screenshots from demo data and update its text |
| [`release`](release/SKILL.md) | Version bump, changelog, privacy scan, commit and push |

## Activating them as skills

Copy the tree into `.claude/skills/`, which is where Claude Code looks (that folder is
git-ignored - this one is the source):

```bat
xcopy docs\skills .claude\skills\ /E /I /Y
```

```bash
cp -r docs/skills/. .claude/skills/
```

They're kept here rather than only in `.claude/` so they stay visible in the repo,
get reviewed like any other file, and work as documentation for humans too. Re-copy
after editing.

## The one runnable piece

```bash
python docs/skills/data-hygiene/check_store.py
```

Read-only audit of `data/store/*.json` - balances vs ledger, junk records, orphaned
foreign keys, silent zero valuations, missing exchange rates, unusable budgets, non-ISO
dates. Exit `0` clean, `1` findings. Never writes anything.

The other tools (demo data, guide screenshots, privacy scan) live in `tools/`.

## Adding a skill

Frontmatter needs `name` (matching the folder) and `description` (when to use it —
this is what gets matched against a task, so be concrete about triggers):

```markdown
---
name: my-skill
description: What it does. Use when <specific trigger>, <another trigger>.
---
```

Keep them specific to *this* repo. General Python or PyQt advice is not worth a skill;
the non-obvious local conventions are — the reversed tuple order between
`STORE_LOAD_ORDER` and `STORE_DUMP_ORDER`, the `insert`/`update` `None` asymmetry, the
`on_change` topic contract.
