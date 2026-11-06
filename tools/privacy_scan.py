#!/usr/bin/env python3
"""Before you push: check that nothing from your real data is in the code repo.

Collects distinctive values from data/store/*.json - account and folio numbers,
contact details, names, notes, and non-round amounts - and searches every file
git would publish (tracked files plus new files that are not ignored). With
--history it also searches everything ever committed. It also flags generic
personal patterns: e-mail addresses, Indian mobile numbers, PAN / IFSC /
Aadhaar-shaped strings and Windows user-profile paths.

Images are NOT inspected - render screenshots from the demo store only
(tools/make_user_guide.py), never from your real data.

Read-only, plain Python, no project imports. Matches are printed only to your
console. Exit 0 = nothing found, 1 = review the findings, 2 = could not run.

Values you have checked and found harmless (placeholder text your records happen
to share, such as "XXXX1234") can go in `.privacy-ignore` at the repo root, one
per line. That file is git-ignored: it comes from your data, so it stays local.

    python tools/privacy_scan.py
    python tools/privacy_scan.py --history
"""
from __future__ import annotations

import argparse
import functools
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Fields whose values are vocabulary, not personal data.
SKIP_KEYS = {
    "account_type", "txn_type", "holding_type", "liability_type", "period", "kind",
    "currency", "frequency", "source_type", "status", "exchange", "market_cap",
    "payout_frequency", "purity", "depository", "investment_segments", "cc_network",
    "loan_type", "icon", "tags", "breakdown_json", "sector",
}
AMOUNT_MIN = 10_000            # smaller sums are too common to mean anything
# Descriptions the app itself writes into records.
APP_TEXT = {"opening balance", "balance reconciliation", "balance reconciliation (1.0 upgrade)",
            "balance adjustment"}
IGNORE_FILE = ROOT / ".privacy-ignore"
# The built app (dist/) is mostly third-party files - library licences with their
# authors' e-mails, colour-map numbers - so it isn't pattern-matched. Instead every
# file in it, binaries included, is searched for *your* identifiers, and nothing an
# app writes beside itself (data/, logs/) may be there at all.
BUNDLE = "dist/"
APP_OUTPUT = re.compile(r"^dist/[^/]+/(data|logs)/")
ALLOWED_EMAILS = {"noreply@anthropic.com"}
PATTERNS = {
    "e-mail address": re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}"),
    "mobile number": re.compile(r"(?<![\d,.])(?:\+91[\s-]?)?[6-9]\d{9}(?![\d,.])"),
    "PAN-shaped": re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
    "IFSC-shaped": re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
    "Aadhaar-shaped": re.compile(r"(?<![\d,.])\d{4} \d{4} \d{4}(?![\d,.])"),
    "user-profile path": re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+(?!<|%|Public\b|you\b)[^\\/\s\"'`]+",
                                    re.IGNORECASE),
}


def _indian(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups) + "," + tail


def _date_like(key: str) -> bool:
    return key.endswith("_date") or key in ("created_at", "updated_at", "as_of", "period_month")


@functools.lru_cache(maxsize=1)
def _ignored() -> frozenset[str]:
    if not IGNORE_FILE.exists():
        return set()
    lines = IGNORE_FILE.read_text(encoding="utf-8-sig").splitlines()
    return frozenset(ln.strip().lower() for ln in lines
                     if ln.strip() and not ln.lstrip().startswith("#"))


def collect(store: Path) -> dict[str, str]:
    """Distinctive value -> where it came from."""
    generic = set(APP_TEXT) | _ignored()
    for folder in (ROOT / "data" / "seed", ROOT / "data" / "reference"):
        for p in folder.glob("*"):
            if p.is_file():
                generic.update(w.lower() for w in re.findall(r"[^\",\n]{4,}",
                                                              p.read_text(encoding="utf-8-sig")))
    values: dict[str, str] = {}
    for path in sorted(store.glob("*.json")):
        try:
            rows = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key, v in row.items():
                if key in SKIP_KEYS or _date_like(key) or key == "id" or key.endswith("_id"):
                    continue
                where = f"{key} in {path.name}"
                if isinstance(v, str):
                    text = v.strip()
                    if len(text) >= 4 and text.lower() not in generic:
                        values.setdefault(text, where)
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    n = abs(float(v))
                    if n >= AMOUNT_MIN and round(n) % 1000:      # non-round sums only
                        whole = int(round(n))
                        for form in (_indian(whole), f"{whole:,}", str(whole)):
                            if form.lower() not in generic:
                                values.setdefault(form, where)
    return values


def own_identifiers() -> list[bytes]:
    """Your user-folder name and the e-mail addresses on this repo's commits."""
    ids = {Path.home().name}
    out = subprocess.run(["git", "log", "--all", "--format=%ae"], cwd=ROOT,
                         capture_output=True, text=True)
    ids |= {e for e in out.stdout.split() if "noreply" not in e}
    return [i.lower().encode() for i in ids if len(i) >= 4]


def scan_bundle_file(label: str, data: bytes, ids: list[bytes], hits: list) -> None:
    low = data.lower()
    for ident in ids:
        if ident in low:
            hits.append((label, 0, f"your identifier '{ident.decode()}' is inside the built app"))


def publishable_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                         cwd=ROOT, capture_output=True, check=True)
    return [ROOT / p for p in out.stdout.decode("utf-8").split("\0") if p]


def _text(path: Path):
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if b"\0" in data[:4096] or len(data) > 5_000_000:
        return None
    return data.decode("utf-8", errors="replace")


def scan_text(label: str, text: str, values: dict[str, str], hits: list) -> None:
    for lineno, line in enumerate(text.splitlines(), 1):
        for value, where in values.items():
            if value in line:
                hits.append((label, lineno, f"'{value}' ({where})"))
        for name, rx in PATTERNS.items():
            for m in rx.finditer(line):
                if m.group(0).lower() in _ignored():
                    continue
                if name == "e-mail address" and (m.group(0) in ALLOWED_EMAILS
                                                 or m.group(0).endswith(("example.com", "example.org"))):
                    continue
                hits.append((label, lineno, f"{name}: {m.group(0)}"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", default=str(ROOT / "data" / "store"))
    ap.add_argument("--history", action="store_true", help="also scan every committed version")
    args = ap.parse_args()
    store = Path(args.store)
    values = collect(store) if store.is_dir() else {}
    if not values:
        print(f"Note: no store at {store} - only the generic patterns are checked.")
    try:
        files = publishable_files()
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"Could not list files with git: {e}", file=sys.stderr)
        return 2

    hits: list = []
    me = Path(__file__).resolve()
    skipped = bundled = 0
    ids = own_identifiers()
    for path in files:
        if path.resolve() == me:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if APP_OUTPUT.match(rel):
            hits.append((rel, 0, "files an app wrote beside its .exe (data/, logs/) must never be published"))
            continue
        if rel.startswith(BUNDLE):
            bundled += 1
            try:
                scan_bundle_file(rel, path.read_bytes(), ids, hits)
            except OSError:
                pass
            continue
        text = _text(path)
        if text is None:
            skipped += 1
            continue
        scan_text(str(path.relative_to(ROOT)), text, values, hits)
    print(f"Scanned {len(files) - skipped - bundled} text files git would publish "
          f"({skipped} binary files such as screenshots not inspected) "
          f"against {len(values)} values from {store}.")
    if bundled:
        print(f"Searched all {bundled} files of the built app in {BUNDLE} (binaries too) for "
              f"your identifiers ({len(ids)}: user-folder name, commit e-mails).")

    if args.history:
        log = subprocess.run(["git", "log", "--all", "-p", "--no-color", "--format=commit %h"],
                             cwd=ROOT, capture_output=True)
        commit, current = "?", "?"
        added: dict[tuple[str, str], list[str]] = {}
        for line in log.stdout.decode("utf-8", errors="replace").splitlines():
            if line.startswith("commit "):
                commit = line.split()[1]
            elif line.startswith("+++ b/"):
                current = line[6:]
            elif line.startswith("+") and not line.startswith("+++"):
                added.setdefault((commit, current), []).append(line[1:])
        for (c, path), lines in added.items():
            if path.endswith("privacy_scan.py"):
                continue
            label = f"history {c}:{path}"
            if APP_OUTPUT.match(path):
                hits.append((label, 0, "files an app wrote beside its .exe were committed"))
            elif path.startswith(BUNDLE):
                scan_bundle_file(label, "\n".join(lines).encode("utf-8", "replace"), ids, hits)
            else:
                scan_text(label, "\n".join(lines), values, hits)

    if not hits:
        print("Nothing personal found.")
        return 0
    print(f"\n{len(hits)} finding(s) - remove them, or confirm each one is not personal:\n")
    for label, lineno, what in hits:
        print(f"  {label}:{lineno}  {what}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
