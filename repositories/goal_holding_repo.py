from __future__ import annotations

from db.connection import Database


class GoalHoldingRepository:
    """Join table goal_holdings (goal_id, holding_id, allocation_pct)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def holding_ids_for_goal(self, goal_id: int) -> list[int]:
        rows = self.db.fetch_all(
            "SELECT holding_id FROM goal_holdings WHERE goal_id = ?", (goal_id,)
        )
        return [r["holding_id"] for r in rows]

    def set_for_goal(
        self, goal_id: int, holding_ids: list[int], allocation_pct: float = 100.0
    ) -> None:
        self.db.execute("DELETE FROM goal_holdings WHERE goal_id = ?", (goal_id,))
        for hid in holding_ids:
            self.db.execute(
                "INSERT OR REPLACE INTO goal_holdings "
                "(goal_id, holding_id, allocation_pct) VALUES (?, ?, ?)",
                (goal_id, hid, allocation_pct),
            )
        self.db.commit()

    def funded_amount(self, goal_id: int) -> float:
        row = self.db.fetch_one(
            "SELECT COALESCE(SUM(h.current_value * gh.allocation_pct / 100.0), 0) AS t "
            "FROM goal_holdings gh "
            "JOIN holdings h ON h.id = gh.holding_id AND h.is_active = 1 "
            "WHERE gh.goal_id = ?",
            (goal_id,),
        )
        return row["t"] if row else 0.0
