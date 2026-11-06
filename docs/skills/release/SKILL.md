---
name: release
description: Prepare a release of the Personal Finance Manager, or any push to a git remote such as GitHub, without leaking personal financial data. Use when bumping the version, writing the changelog, committing for publication, or before every git push. Covers the privacy scan, version and changelog, checks, screenshots, the MIT license and the push itself.
---

# Releasing and pushing

The repository is meant to be safe to publish: personal data lives only in
`data/store/`, `data/user/`, `logs/` and `shots/`, and all of them are
git-ignored. Every release has to keep it that way. Code can be fixed later,
but a pushed secret can't be taken back.

## 1. Privacy scan - before every push

```bat
.venv\Scripts\python tools\privacy_scan.py --history
```

It reads your local store (read-only) and searches every file git would publish,
and with `--history` everything ever committed, for:

- distinctive values from your data: account and folio numbers, contact details,
  names, notes, and non-round amounts in several formats;
- personal patterns: e-mail addresses, Indian mobile numbers, PAN-, IFSC- and
  Aadhaar-shaped strings, and `C:\Users\<name>` paths.

Some matches are harmless: UI placeholder text (`XXXX1234`, `HDFC0001234`) or
sample names in tests that your data happens to share. Once you've checked one, add
it to `.privacy-ignore` at the repo root, one value per line, so it stops coming
back. That file is git-ignored because its contents come from your data. Other
matches are real: an amount from your accounts written into a document, a figure
in `STATUS.md`, a path with your user name. Remove those, then scan again.

- **Images are not scanned.** Every committed image must come from
  `tools/make_user_guide.py`, which uses the fictional demo store.
- **Already committed something personal?** Deleting it in a new commit leaves it
  in history. Don't push. Rewrite the unpushed history first, for example by
  re-committing from a clean tree on a new orphan branch.
- **Your commit e-mail becomes public** on GitHub. To hide it, use GitHub's noreply
  address before committing:
  `git config user.email <id>+<username>@users.noreply.github.com`.

## 2. Version and notes

- `APP_VERSION` in `config/settings.py`, using semantic versioning: a new feature
  is a minor bump (1.1.0 → 1.2.0), a fix is a patch (1.1.0 → 1.1.1).
  `STORE_VERSION` is separate and changes only with a store migration.
- `CHANGELOG.md`: newest first, written for users, with a date.
- `STATUS.md`: update *Health* (test count and what was actually verified) and
  the open gaps.

## 3. Checks

- The **verify-changes** skill: compileall, the layering grep, the full test
  suite (write down the count), and `check_store.py` on a copy of the store.
- The **user-guide** skill, if anything visible changed.
- If you will attach an `.exe` to the release: run `run_build_exe.bat`, then open
  the built app once.

## 4. Commit and push

```bat
git status                         :: nothing from data\, logs\, shots\, .venv\ or dist\
git add -A
git commit -m "Release 1.x.y: ..."
git tag v1.x.y                     :: optional
:: first push to a new GitHub repository:
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main --tags
```

- Never `git add -f` an ignored path.
- The license is MIT (`LICENSE`). Update the year range in its copyright line
  when it changes.
- `.gitattributes` keeps `.bat` files in CRLF format, which `cmd.exe` needs,
  and marks images as binary.
