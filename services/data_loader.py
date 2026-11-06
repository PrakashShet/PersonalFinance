"""Data loader — reads CSV/JSON files from `data/` and populates SQLite.

This runs once at application startup. The contract is:
  * `data/seed/*`       — ships with the app (categories, account types, stock master)
  * `data/store/*`      — the user's actual records (accounts, transactions, holdings...)
  * `data/reference/*`  — static reference (tax slabs, inflation rates)
  * `data/cache/*`      — auto-refreshed (NAV, prices)

Files are loaded in dependency order to satisfy foreign keys.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from db.connection import Database
from utils.csv_handler import read_csv
from utils.json_handler import read_json
from utils.logger import get_logger

log = get_logger(__name__)


# Load order matters because of FK constraints
STORE_LOAD_ORDER = [
    ("accounts.json",        "accounts"),
    ("categories.json",      "categories"),
    ("income_sources.json",  "income_sources"),
    ("holdings.json",        "holdings"),
    ("liabilities.json",     "liabilities"),
    ("goals.json",           "goals"),
    ("goal_holdings.json",   "goal_holdings"),
    ("transactions.json",    "transactions"),
    ("income_entries.json",  "income_entries"),
    ("holding_valuations.json", "holding_valuations"),
    ("net_worth_snapshots.json", "net_worth_snapshots"),
    ("reminders.json",       "reminders"),
]


class DataLoader:
    def __init__(self, db: Database) -> None:
        self.db = db

    # --- public API -------------------------------------------------------
    def load_seed_data(self, seed_dir: Path) -> None:
        """Categories, account types, stock-cap master — ship with the app."""
        seed_dir.mkdir(parents=True, exist_ok=True)

        # Categories (JSON)
        cat_file = seed_dir / "categories.json"
        if cat_file.exists() and self._is_empty("categories"):
            data = read_json(cat_file)
            self._bulk_insert("categories", data)
            log.info(f"Loaded {len(data)} seed categories.")

        # Stock master (CSV) — table may not exist until schema adds it
        stock_file = seed_dir / "stock_master.csv"
        if (
            stock_file.exists()
            and self._table_exists("stock_master")
            and self._is_empty("stock_master")
        ):
            rows = read_csv(stock_file)
            self._bulk_insert("stock_master", rows)
            log.info(f"Loaded {len(rows)} stock master rows.")

    def load_store_data(self, store_dir: Path) -> None:
        """User's actual records. Wipes SQLite tables then refills from disk
        so the CSV/JSON files remain the source of truth."""
        store_dir.mkdir(parents=True, exist_ok=True)

        for filename, table in STORE_LOAD_ORDER:
            path = store_dir / filename
            if not path.exists():
                # Create empty file so it's discoverable by the user
                path.write_text("[]", encoding="utf-8")
                continue
            try:
                data = read_json(path)
            except json.JSONDecodeError as e:
                log.error(f"Bad JSON in {path}: {e}")
                continue
            # Full refresh: wipe even when the file is empty, so a store
            # file emptied by the user also clears stale rows in a
            # persistent app.db from a previous session.
            self.db.execute(f"DELETE FROM {table};")
            if not data:
                continue
            self._bulk_insert(table, data)
            log.info(f"Loaded {len(data)} rows into '{table}' from {filename}.")
        self.db.commit()

    def load_reference_data(self, ref_dir: Path) -> None:
        """Static reference like tax slabs and inflation rates."""
        ref_dir.mkdir(parents=True, exist_ok=True)
        for path in ref_dir.glob("*.json"):
            key = path.stem
            value = read_json(path)
            self.db.execute(
                "INSERT OR REPLACE INTO reference_data (key, value_json) VALUES (?, ?)",
                (key, json.dumps(value)),
            )
        self.db.commit()

    # --- helpers ----------------------------------------------------------
    def _table_exists(self, table: str) -> bool:
        row = self.db.fetch_one(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        )
        return row is not None

    def _is_empty(self, table: str) -> bool:
        if not self._table_exists(table):
            return True
        row = self.db.fetch_one(f"SELECT COUNT(*) AS c FROM {table}")
        return (row["c"] if row else 0) == 0

    def _bulk_insert(self, table: str, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        # Use the union of all keys so we tolerate slightly-different rows
        all_keys: list[str] = []
        seen: set[str] = set()
        for r in rows:
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    all_keys.append(k)
        cols = ", ".join(all_keys)
        placeholders = ", ".join(["?"] * len(all_keys))
        sql = f"INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})"
        values = [tuple(r.get(k) for k in all_keys) for r in rows]
        self.db.executemany(sql, values)
