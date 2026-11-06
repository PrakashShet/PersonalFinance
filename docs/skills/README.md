# Project skills

Task playbooks for this repo. Each folder holds a `SKILL.md` with YAML frontmatter,
so they work both as plain documentation and as loadable skills.

| Skill | Use when |
|-------|----------|
| [`add-entity`](add-entity/SKILL.md) | Adding a new tracked record type — the ordered 8-step path from `schema.sql` through to a registered view, including the two persistence-wiring steps that fail silently if missed |
| [`add-view`](add-view/SKILL.md) | Adding or editing a PyQt6 view — dependency injection, the lazy refresh contract, styling, and why a tab shows stale data |
| [`verify-changes`](verify-changes/SKILL.md) | Before calling any change done — tiered checks, what runs in a sandbox vs. what needs Windows, and honest reporting |
| [`data-hygiene`](data-hygiene/SKILL.md) | Numbers look wrong, after bulk edits, or as a periodic audit of `data/store/` |

## Activating them as skills

Copy the tree into `.claude/skills/`, which is where Claude Code and Cowork look:

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

Read-only audit of `data/store/*.json` — junk records, orphaned foreign keys, silent
zero valuations, mixed currencies, non-ISO dates. Exit `0` clean, `1` findings.
Never writes anything.

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
