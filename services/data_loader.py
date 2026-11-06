"""Data loader - reads the JSON store (and seed / reference files) into SQLite.

Contract:
  * ``data/seed/*``       ships with the app (categories, stock master)
  * ``data/store/*``      the user's records - the source of truth
  * ``data/reference/*``  static reference (tax slabs, assumptions)

The store is read **strictly**. A file that cannot be decoded or parsed, that
does not hold a list of records, or that carries fields this version does not
know raises :class:`StoreLoadError` instead of being skipped. Skipping used to
leave the table empty, and the next autosave then overwrote the damaged file
with that emptiness - turning a recoverable problem into permanent data loss.

Files are loaded in dependency order to satisfy foreign keys.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

from db.connection import Database
from utils.csv_handler import read_csv
from utils.json_handler import read_json, write_text_atomic
from utils.logger import get_logger

log = get_logger(__name__)


# Load order matters because of FK constraints. Mirrored (reversed tuples) by
# STORE_DUMP_ORDER in services/data_persister.py - change both together.
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
    ("fx_rates.json",        "fx_rates"),
    ("budgets.json",         "budgets"),
]

StoreTables = dict[str, Optional[list[dict[str, Any]]]]


class StoreLoadError(Exception):
    """A store file could not be read safely. Nothing has been written."""

    def __init__(self, path: Path, reason: str) -> None:
        self.path = Path(path)
        self.reason = reason
        super().__init__(f"{self.path.name} {reason}")


def read_store_file(path: Path) -> Optional[list[dict[str, Any]]]:
    """Parse one store file. ``None`` if it does not exist; raises on damage."""
    path = Path(path)
    if not path.exists():
        return None
    try:
        text = path.read_bytes().decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise StoreLoadError(path, f"is not valid UTF-8 text (byte {e.start}).") from e
    except OSError as e:
        raise StoreLoadError(path, f"could not be read ({e.strerror or e}).") from e
    if not text.strip():
        # The app always writes at least "[]"; an empty file means a write
        # was cut short.
        raise StoreLoadError(path, "is empty - it was probably cut short while saving.")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise StoreLoadError(
            path, f"is not valid JSON (line {e.lineno}, column {e.colno}: {e.msg})."
        ) from e
    if not isinstance(data, list):
        raise StoreLoadError(
            path, f"should hold a list of records but holds a {type(data).__name__}."
        )
    for i, row in enumerate(data, start=1):
        if not isinstance(row, dict):
            raise StoreLoadError(path, f"record #{i} is not a JSON object.")
    return data


def read_store(store_dir: Path) -> StoreTables:
    """Read and validate every store file. Raises before anything is loaded."""
    return {
        filename: read_store_file(Path(store_dir) / filename)
        for filename, _table in STORE_LOAD_ORDER
    }


class DataLoader:
    def __init__(self, db: Database) -> None:
        self.db = db

    # --- public API -------------------------------------------------------
    def load_seed_data(self, seed_dir: Path) -> None:
        """Categories and the stock master - ship with the app."""
        seed_dir.mkdir(parents=True, exist_ok=True)

        cat_file = seed_dir / "categories.json"
        if cat_file.exists() and self._is_empty("categories"):
            data = read_json(cat_file)
            self._insert_rows("categories", data)
            log.info(f"Loaded {len(data)} seed categories.")

        stock_file = seed_dir / "stock_master.csv"
        if (
            stock_file.exists()
            and self._table_exists("stock_master")
            and self._is_empty("stock_master")
        ):
            rows = [
                {k: (v or None) for k, v in r.items()}
                for r in read_csv(stock_file)
                if (r.get("symbol") or "").strip()
            ]
            self._insert_rows("stock_master", rows)
            log.info(f"Loaded {len(rows)} stock master rows.")
        self.db.commit()

    def load_store_data(
        self, store_dir: Path, data: Optional[StoreTables] = None
    ) -> None:
        """Wipe each store table and refill it from disk (or from ``data``,
        already read and validated by :func:`read_store`).

        A missing file is created as ``[]`` and its table left as-is, so seed
        rows (categories) survive a first run. An existing file - even ``[]`` -
        replaces the table's contents.
        """
        store_dir = Path(store_dir)
        store_dir.mkdir(parents=True, exist_ok=True)
        tables = data if data is not None else read_store(store_dir)

        for filename, table in STORE_LOAD_ORDER:
            path = store_dir / filename
            rows = tables.get(filename)
            if rows is None:
                write_text_atomic(path, "[]\n")
                continue
            self._check_columns(path, table, rows)
            self.db.execute(f"DELETE FROM {table};")
            if rows:
                try:
                    self._insert_rows(table, rows)
                except sqlite3.IntegrityError as e:
                    self.db.conn.rollback()
                    raise StoreLoadError(
                        path,
                        f"has a record the database rejected ({e}). Run "
                        "docs/skills/data-hygiene/check_store.py for details.",
                    ) from e
                log.info(f"Loaded {len(rows)} rows into '{table}' from {filename}.")
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

    def _columns(self, table: str) -> set[str]:
        return {r["name"] for r in self.db.fetch_all(f"PRAGMA table_info({table})")}

    def _check_columns(self, path: Path, table: str, rows: list[dict]) -> None:
        """Refuse fields the schema can't hold - loading would silently drop
        them, and the next save would erase them from disk."""
        present: set[str] = set()
        for r in rows:
            present.update(r.keys())
        unknown = present - self._columns(table)
        if unknown:
            raise StoreLoadError(
                path,
                "has field(s) this version of the app does not know: "
                f"{', '.join(sorted(unknown))}. It may have been written by a "
                "newer version - nothing was loaded so they are not lost.",
            )

    def _defaulted_not_null(self, table: str) -> set[str]:
        """Columns declared NOT NULL with a DEFAULT."""
        return {
            r["name"] for r in self.db.fetch_all(f"PRAGMA table_info({table})")
            if r["notnull"] and r["dflt_value"] is not None
        }

    def _insert_rows(self, table: str, rows: list[dict[str, Any]]) -> None:
        """Insert rows in order. Consecutive rows with the same fields share one
        statement; a row lacking a field lets the column's default apply.

        A ``null`` in a column declared ``NOT NULL DEFAULT x`` also gets the
        default: databases created by older versions added such columns
        without the constraint, so their dumps legitimately contain nulls
        (e.g. ``accounts.cc_credit_limit``)."""
        defaulted = self._defaulted_not_null(table)
        batch: list[dict[str, Any]] = []
        batch_keys: tuple[str, ...] = ()
        for row in rows:
            if defaulted:
                row = {k: v for k, v in row.items() if not (v is None and k in defaulted)}
            keys = tuple(row.keys())
            if batch and keys != batch_keys:
                self._insert_batch(table, batch_keys, batch)
                batch = []
            batch_keys = keys
            batch.append(row)
        if batch:
            self._insert_batch(table, batch_keys, batch)

    def _insert_batch(self, table: str, keys: tuple[str, ...], rows: list[dict]) -> None:
        if not keys:
            for _ in rows:
                self.db.execute(f"INSERT INTO {table} DEFAULT VALUES")
            return
        cols = ", ".join(keys)
        placeholders = ", ".join(["?"] * len(keys))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        self.db.executemany(sql, [tuple(r.get(k) for k in keys) for r in rows])
