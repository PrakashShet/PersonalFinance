"""SQLite connection manager — singleton, thread-safe enough for desktop use."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)


class Database:
    """Thin wrapper around sqlite3 with helpers used across repositories."""

    def __init__(self) -> None:
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected. Call db.connect() first.")
        return self._conn

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    def connect(self, path: Path | str) -> None:
        """Open a database file, or an in-memory scratch DB for ``":memory:"``."""
        target = str(path)
        in_memory = target == ":memory:"
        if not in_memory:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(target, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        if not in_memory:
            self._conn.execute("PRAGMA journal_mode = WAL;")
        log.info("Connected to SQLite %s", "in memory" if in_memory else f"at {path}")

    def apply_schema(self, schema_path: Path) -> None:
        sql = schema_path.read_text(encoding="utf-8")
        self.conn.executescript(sql)
        self.conn.commit()
        log.info("Schema applied.")

    def execute(self, query: str, params: tuple = ()) -> sqlite3.Cursor:
        cur = self.conn.execute(query, params)
        return cur

    def executemany(self, query: str, seq_of_params) -> sqlite3.Cursor:
        return self.conn.executemany(query, seq_of_params)

    def fetch_all(self, query: str, params: tuple = ()) -> list[sqlite3.Row]:
        return self.execute(query, params).fetchall()

    def fetch_one(self, query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        return self.execute(query, params).fetchone()

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.commit()
            self._conn.close()
            self._conn = None
            log.info("SQLite connection closed.")


# Singleton instance imported across the app
db = Database()
