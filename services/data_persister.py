"""Data persister - writes SQLite tables back to the JSON store, and backups.

Saving
    * Every file is written atomically (temp file + ``os.replace``), so a crash
      mid-save leaves the previous version intact rather than a truncated file.
    * A file whose content would not change is not rewritten at all.
    * All tables are read first and written second: a read error aborts the
      save before anything on disk is touched.
    * A table that suddenly reads as empty while its file holds many records is
      refused (see ``WIPE_GUARD_MIN_ROWS``) - that pattern is a bug, not an edit.

Backups
    ``data/user/backups/<YYYYMMDD_HHMMSS>[_label]/`` - a full copy of the store.
    Taken at startup (after the store validated), before a format migration,
    on clean shutdown, and on demand. A backup identical to the newest one is
    skipped. Retention is tiered so a long history survives busy days::

        newest 30 backups (what older versions kept)
        + the newest backup of each of the last 30 days
        + the newest of each of the last 24 months
        + the newest of every year, forever
        + every "manual" and "pre-migration" backup, forever

    Optionally every backup is also copied to a second folder (Settings - e.g. a
    OneDrive folder), so a copy survives the loss of this disk.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from db.connection import Database
from utils.json_handler import dumps_records, write_text_atomic
from utils.logger import get_logger

log = get_logger(__name__)


STORE_DUMP_ORDER = [
    ("accounts",              "accounts.json"),
    ("categories",            "categories.json"),
    ("income_sources",        "income_sources.json"),
    ("holdings",              "holdings.json"),
    ("liabilities",           "liabilities.json"),
    ("goals",                 "goals.json"),
    ("goal_holdings",         "goal_holdings.json"),
    ("transactions",          "transactions.json"),
    ("income_entries",        "income_entries.json"),
    ("holding_valuations",    "holding_valuations.json"),
    ("net_worth_snapshots",   "net_worth_snapshots.json"),
    ("reminders",             "reminders.json"),
    ("fx_rates",              "fx_rates.json"),
    ("budgets",               "budgets.json"),
]

# Refuse to replace a file holding at least this many records with an empty
# table. Deleting records one by one never trips it; a wiped table does.
WIPE_GUARD_MIN_ROWS = 10

# --- backup retention -------------------------------------------------------
KEEP_NEWEST = 30          # matches the pre-1.0 policy, so upgrading never deletes more
KEEP_DAILY_DAYS = 30
KEEP_MONTHLY_MONTHS = 24
KEEP_FOREVER_LABELS = ("manual", "pre-migration")

BACKUP_NAME = re.compile(r"^(\d{8}_\d{6})(?:_([A-Za-z0-9-]+))?$")


class SaveRefused(Exception):
    """The save was aborted to protect data already on disk."""


@dataclass
class SaveResult:
    written: list[str] = field(default_factory=list)
    unchanged: int = 0


class DataPersister:
    def __init__(self, db: Database) -> None:
        self.db = db

    def dump_store_data(self, store_dir: Path, make_backup: bool = False) -> SaveResult:
        store_dir = Path(store_dir)
        store_dir.mkdir(parents=True, exist_ok=True)

        if make_backup:
            backup_store(store_dir, default_backup_root(store_dir), label="")

        # 1. Read everything first - a failure here writes nothing.
        payloads: dict[str, tuple[str, int]] = {}
        for table, filename in STORE_DUMP_ORDER:
            rows = self.db.fetch_all(f"SELECT * FROM {table} ORDER BY rowid")
            payloads[filename] = (dumps_records([dict(r) for r in rows]), len(rows))

        # 2. Guard against writing a wiped table over real data.
        for filename, (_text, count) in payloads.items():
            path = store_dir / filename
            if count == 0 and path.exists():
                existing = _count_records(path)
                if existing >= WIPE_GUARD_MIN_ROWS:
                    raise SaveRefused(
                        f"Refusing to replace {existing} records in {filename} "
                        "with an empty table."
                    )

        # 3. Write only what changed, atomically.
        result = SaveResult()
        for filename, (text, count) in payloads.items():
            path = store_dir / filename
            if _read_text(path) == text:
                result.unchanged += 1
                continue
            write_text_atomic(path, text)
            result.written.append(filename)
            log.info(f"Saved {count:>5} rows -> {filename}")
        return result


# --------------------------------------------------------------------------
# Backups
# --------------------------------------------------------------------------

def default_backup_root(store_dir: Path) -> Path:
    return Path(store_dir).parent / "user" / "backups"


def store_digest(folder: Path) -> str:
    """Content hash of a store folder's JSON files (names + bytes)."""
    h = hashlib.sha256()
    for p in sorted(Path(folder).glob("*.json")):
        h.update(p.name.encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def list_backups(backup_root: Path) -> list[Path]:
    """Backup folders, oldest first (folders not named like backups are ignored)."""
    root = Path(backup_root)
    if not root.is_dir():
        return []
    found = [p for p in root.iterdir() if p.is_dir() and BACKUP_NAME.match(p.name)]
    # Timestamp first; within the same second, creation order (the label
    # would otherwise sort "shutdown" before "startup" regardless of time).
    return sorted(found, key=lambda p: (p.name[:15], p.stat().st_ctime_ns, p.name))


def latest_backup(backup_root: Path) -> Optional[Path]:
    backups = list_backups(backup_root)
    return backups[-1] if backups else None


def backup_store(
    store_dir: Path,
    backup_root: Path,
    label: str = "",
    mirror_root: Optional[Path] = None,
    now: Optional[datetime] = None,
) -> Optional[Path]:
    """Copy the store into a new timestamped folder. Returns it (or the newest
    existing backup when nothing changed since), or ``None`` for an empty store."""
    store_dir, backup_root = Path(store_dir), Path(backup_root)
    files = sorted(store_dir.glob("*.json")) if store_dir.is_dir() else []
    if not files:
        return None

    newest = latest_backup(backup_root)
    keep_always = label.startswith(KEEP_FOREVER_LABELS)
    if newest is not None and not keep_always and store_digest(newest) == store_digest(store_dir):
        return newest

    now = now or datetime.now()
    name = now.strftime("%Y%m%d_%H%M%S") + (f"_{label}" if label else "")
    dest = backup_root / name
    n = 1
    while dest.exists():
        n += 1
        dest = backup_root / f"{name}-{n}" if label else backup_root / f"{name}_{n}"
    tmp = backup_root / f".{dest.name}.partial"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for f in files:
        shutil.copy2(f, tmp / f.name)
    _finish_backup(tmp, dest)
    log.info(f"Backup created at {dest}")

    prune_backups(backup_root, now)
    if mirror_root:
        try:
            mirror_backup(dest, Path(mirror_root), now)
        except OSError as e:
            log.error(f"Could not copy backup to {mirror_root}: {e}")
    return dest


def _finish_backup(tmp: Path, dest: Path) -> None:
    """Rename the finished ``.partial`` folder into place.

    On Windows, antivirus or the search indexer often holds freshly written
    files for a moment, and renaming their folder fails with "Access is
    denied". Retry briefly, then fall back to copying (the backup is complete
    either way; only the all-at-once appearance is lost)."""
    import time

    for attempt in range(8):
        try:
            tmp.rename(dest)
            return
        except PermissionError:
            time.sleep(0.1 * (attempt + 1))
    shutil.copytree(tmp, dest)
    shutil.rmtree(tmp, ignore_errors=True)


def mirror_backup(backup: Path, mirror_root: Path, now: Optional[datetime] = None) -> Path:
    mirror_root.mkdir(parents=True, exist_ok=True)
    target = mirror_root / backup.name
    if not target.exists():
        shutil.copytree(backup, target)
        log.info(f"Backup mirrored to {target}")
    prune_backups(mirror_root, now or datetime.now())
    return target


def _parse(name: str) -> Optional[tuple[datetime, str]]:
    m = BACKUP_NAME.match(name)
    if not m:
        return None
    try:
        ts = datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
    except ValueError:
        return None
    return ts, (m.group(2) or "")


def backups_to_keep(names: list[str], now: datetime) -> set[str]:
    """Pure retention policy: which backup folder names survive pruning."""
    parsed = [(n, *p) for n in names if (p := _parse(n)) is not None]
    parsed.sort(key=lambda x: x[0], reverse=True)          # newest first
    keep: set[str] = set()

    for name, _ts, label in parsed:
        if label.startswith(KEEP_FOREVER_LABELS):
            keep.add(name)
    for name, _ts, _label in parsed[:KEEP_NEWEST]:
        keep.add(name)

    seen_day: set[str] = set()
    seen_month: set[str] = set()
    seen_year: set[str] = set()
    day_cutoff = now - timedelta(days=KEEP_DAILY_DAYS)
    month_index_now = now.year * 12 + now.month
    for name, ts, _label in parsed:                          # newest first
        day, month, year = ts.strftime("%Y%m%d"), ts.strftime("%Y%m"), ts.strftime("%Y")
        if ts >= day_cutoff and day not in seen_day:
            keep.add(name)
        seen_day.add(day)
        if month_index_now - (ts.year * 12 + ts.month) < KEEP_MONTHLY_MONTHS and month not in seen_month:
            keep.add(name)
        seen_month.add(month)
        if year not in seen_year:
            keep.add(name)
        seen_year.add(year)
    return keep


def prune_backups(backup_root: Path, now: Optional[datetime] = None) -> list[str]:
    """Delete backups the retention policy doesn't keep. Returns removed names.
    Folders that don't look like backups are never touched."""
    backup_root = Path(backup_root)
    if not backup_root.is_dir():
        return []
    for stale in backup_root.glob(".*.partial"):
        shutil.rmtree(stale, ignore_errors=True)
    names = [p.name for p in list_backups(backup_root)]
    keep = backups_to_keep(names, now or datetime.now())
    removed = []
    for name in names:
        if name not in keep:
            shutil.rmtree(backup_root / name, ignore_errors=True)
            removed.append(name)
    if removed:
        log.info(f"Pruned {len(removed)} old backup(s) from {backup_root}")
    return removed


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _count_records(path: Path) -> int:
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return len(data) if isinstance(data, list) else 0
    except (OSError, ValueError):
        return 0
