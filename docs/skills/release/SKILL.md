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
- **The built app (`dist/`) is checked differently.** Its third-party files contain
  other people's public e-mails and numbers (library licences, colour maps), so they
  aren't pattern-matched. Instead every file in it, binaries included, is searched for
  *your* identifiers: your user-folder name and the e-mails on this repo's commits.
  Anything an app wrote beside its `.exe` (`data/`, `logs/`) is always a finding.
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

## 4. The built app

The ready-to-run Windows app is committed in `dist/PersonalFinanceManager/`, so people can
download it without Python. For each release:

1. `run_build_exe.bat` (it sets aside and restores any old data beside the `.exe`).
2. Launch it once, ideally with `PFM_HOME` set to a throwaway folder.
3. `git status dist` must list only `dist/PersonalFinanceManager/PersonalFinanceManager.exe`
   and files under `_internal/`, never `data/` or `logs/`. The ignore rules allow only
   that, and re-include `*.pyd` (the Qt modules), which `*.py[cod]` would otherwise drop.
4. Commit it with the release.

Size limits: a `git push` accepts files up to 100 MB (the largest app file is about
20 MB). GitHub's website accepts uploads up to 25 MB. A Release asset can be up to 2 GB,
but only through the *Attach binaries* box; a file dropped into the description box
hits the 25 MB limit.

## 5. Commit and push

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
