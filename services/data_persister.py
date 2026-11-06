"""Data persister — dumps SQLite tables back to CSV/JSON files in data/store.

Runs on graceful shutdown (and periodically via autosave). Keeps the
human-readable files as the canonical source of truth.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from db.connection import Database
from utils.logger import get_logger

log = get_logger(__name__)

# How many timestamped rollback snapshots to retain under data/user/backups.
MAX_BACKUPS = 30


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
]


class DataPersister:
    def __init__(self, db: Database) -> None:
        self.db = db

    def dump_store_data(self, store_dir: Path, make_backup: bool = True) -> None:
        store_dir.mkdir(parents=True, exist_ok=True)

        if make_backup:
            self._backup_existing(store_dir)

        for table, filename in STORE_DUMP_ORDER:
            try:
                rows = self.db.fetch_all(f"SELECT * FROM {table}")
            except Exception as e:
                log.error(f"Failed to read table {table}: {e}")
                continue
            data = [dict(r) for r in rows]
            out_path = store_dir / filename
            out_path.write_text(
                json.dumps(data, indent=2, default=str, ensure_ascii=False),
                encoding="utf-8",
            )
            log.info(f"Dumped {len(data):>5} rows: {table} -> {filename}")

    def _backup_existing(self, store_dir: Path) -> None:
        """Snapshot the current store/ into data/user/backups/<timestamp>/."""
        backup_root = store_dir.parent / "user" / "backups"
        backup_root.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = backup_root / ts
        if any(store_dir.iterdir()):
            shutil.copytree(store_dir, dest)
            log.info(f"Backup created at {dest}")

        # Retain the most recent backups. Each backup is a full snapshot of the
        # store, so the live store always holds complete history regardless of
        # how many rollback points we keep.
        self._prune_backups(backup_root, keep=MAX_BACKUPS)

    @staticmethod
    def _prune_backups(backup_root: Path, keep: int) -> None:
        existing = sorted(
            (p for p in backup_root.glob("*") if p.is_dir()), reverse=True
        )
        for old in existing[keep:]:
            shutil.rmtree(old, ignore_errors=True)
