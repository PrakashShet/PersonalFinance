from __future__ import annotations

from typing import Optional

from models.transaction import Transaction
from repositories.base_repo import BaseRepository


class TransactionRepository(BaseRepository[Transaction]):
    table_name = "transactions"
    model_class = Transaction

    def list_recent(self, limit: int = 50) -> list[Transaction]:
        rows = self.db.fetch_all(
            "SELECT * FROM transactions ORDER BY txn_date DESC, id DESC LIMIT ?",
            (limit,),
        )
        return [Transaction.from_row(r) for r in rows]

    def list_filtered(
        self,
        year: Optional[str] = None,
        month: Optional[str] = None,
        txn_type: Optional[str] = None,
        account_id: Optional[int] = None,
        category_id: Optional[int] = None,
        search: Optional[str] = None,
    ) -> list:
        """Joined display rows with account / counter / category names."""
        where: list[str] = []
        params: list = []
        if year:
            where.append("strftime('%Y', t.txn_date) = ?")
            params.append(str(year))
        if month:
            where.append("strftime('%m', t.txn_date) = ?")
            params.append(f"{int(month):02d}")
        if txn_type:
            where.append("t.txn_type = ?")
            params.append(txn_type)
        if account_id:
            where.append("(t.account_id = ? OR t.counter_account_id = ?)")
            params.extend([account_id, account_id])
        if category_id:
            where.append("t.category_id = ?")
            params.append(category_id)
        if search:
            where.append(
                "(t.description LIKE ? OR t.reference_no LIKE ? OR t.tags LIKE ?)"
            )
            like = f"%{search}%"
            params.extend([like, like, like])

        sql = (
            "SELECT t.*, a.name AS account_name, "
            "ca.name AS counter_account_name, c.name AS category_name "
            "FROM transactions t "
            "LEFT JOIN accounts a ON a.id = t.account_id "
            "LEFT JOIN accounts ca ON ca.id = t.counter_account_id "
            "LEFT JOIN categories c ON c.id = t.category_id"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY t.txn_date DESC, t.id DESC"
        return self.db.fetch_all(sql, tuple(params))

    def period_summary(
        self, year: Optional[str] = None, month: Optional[str] = None
    ) -> dict:
        """Sum of amount grouped by txn_type for the given period."""
        where: list[str] = []
        params: list = []
        if year:
            where.append("strftime('%Y', txn_date) = ?")
            params.append(str(year))
        if month:
            where.append("strftime('%m', txn_date) = ?")
            params.append(f"{int(month):02d}")
        sql = "SELECT txn_type, COALESCE(SUM(amount), 0) AS total FROM transactions"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " GROUP BY txn_type"
        rows = self.db.fetch_all(sql, tuple(params))
        return {r["txn_type"]: r["total"] for r in rows}

    def distinct_years(self) -> list[str]:
        rows = self.db.fetch_all(
            "SELECT DISTINCT strftime('%Y', txn_date) AS y "
            "FROM transactions ORDER BY y DESC"
        )
        return [r["y"] for r in rows if r["y"]]
