"""Lightweight access to the categories table (no dedicated model)."""
from __future__ import annotations

from db.connection import Database


class CategoryRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def list_by_kind(self, kind: str) -> list:
        """Rows (id, name, kind) for 'income' or 'expense', alphabetical."""
        return self.db.fetch_all(
            "SELECT id, name, kind FROM categories WHERE kind = ? ORDER BY name",
            (kind,),
        )

    def list_all(self) -> list:
        return self.db.fetch_all(
            "SELECT id, name, kind FROM categories ORDER BY kind, name"
        )

    def name_map(self) -> dict:
        return {r["id"]: r["name"] for r in self.list_all()}

    def get(self, category_id: int):
        """Row (id, name, kind) or None."""
        return self.db.fetch_one(
            "SELECT id, name, kind FROM categories WHERE id = ?", (category_id,)
        )

    def get_id_by_name(self, name: str, kind: str) -> int | None:
        row = self.db.fetch_one(
            "SELECT id FROM categories WHERE name = ? AND kind = ?",
            (name, kind),
        )
        return row["id"] if row else None

    def ensure(self, name: str, kind: str, icon: str = "") -> int:
        """Return category id, inserting the row if it does not exist yet."""
        existing = self.get_id_by_name(name, kind)
        if existing is not None:
            return existing
        self.db.execute(
            "INSERT INTO categories (name, kind, icon) VALUES (?, ?, ?)",
            (name, kind, icon or None),
        )
        self.db.commit()
        row = self.db.fetch_one("SELECT last_insert_rowid() AS id")
        return row["id"]
