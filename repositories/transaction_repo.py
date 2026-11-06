from __future__ import annotations

from typing import Optional

from models.transaction import Transaction
from repositories.base_repo import BaseRepository

# SQL mirror of services/ledger.py: signed effect on the *primary* account.
_PRIMARY_EFFECT = (
    "CASE "
    "WHEN txn_type IN ('income', 'investment_sell', 'adjustment') THEN amount "
    "WHEN txn_type IN ('expense', 'investment_buy', 'transfer') THEN -amount "
    "ELSE 0 END"
)


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
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: Optional[int] = None,
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
        if date_from:
            where.append("t.txn_date >= ?")
            params.append(date_from)
        if date_to:
            where.append("t.txn_date <= ?")
            params.append(date_to)
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
                "(t.description LIKE ? OR t.reference_no LIKE ? OR t.tags LIKE ?"
                " OR c.name LIKE ? OR a.name LIKE ?)"
            )
            like = f"%{search}%"
            params.extend([like, like, like, like, like])

        sql = (
            "SELECT t.*, a.name AS account_name, a.currency AS account_currency, "
            "ca.name AS counter_account_name, c.name AS category_name "
            "FROM transactions t "
            "LEFT JOIN accounts a ON a.id = t.account_id "
            "LEFT JOIN accounts ca ON ca.id = t.counter_account_id "
            "LEFT JOIN categories c ON c.id = t.category_id"
        )
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY t.txn_date DESC, t.id DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return self.db.fetch_all(sql, tuple(params))

    def period_summary(
        self,
        year: Optional[str] = None,
        month: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
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
        if date_from:
            where.append("txn_date >= ?")
            params.append(date_from)
        if date_to:
            where.append("txn_date <= ?")
            params.append(date_to)
        sql = "SELECT txn_type, COALESCE(SUM(amount), 0) AS total FROM transactions"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " GROUP BY txn_type"
        rows = self.db.fetch_all(sql, tuple(params))
        return {r["txn_type"]: r["total"] for r in rows}

    def expense_total(
        self, year: str, month: str, exclude_tag_prefix: Optional[str] = None
    ) -> float:
        """Expenses in a month, optionally excluding entries whose tags start
        with a prefix (e.g. ``emi:`` - EMIs are projected separately)."""
        sql = (
            "SELECT COALESCE(SUM(amount), 0) AS total FROM transactions "
            "WHERE txn_type = 'expense' AND strftime('%Y', txn_date) = ? "
            "AND strftime('%m', txn_date) = ?"
        )
        params: list = [str(year), f"{int(month):02d}"]
        if exclude_tag_prefix:
            sql += " AND COALESCE(tags, '') NOT LIKE ?"
            params.append(f"{exclude_tag_prefix}%")
        row = self.db.fetch_one(sql, tuple(params))
        return float(row["total"]) if row else 0.0

    def expense_totals(
        self,
        date_from: str,
        date_until: str,
        category_id: Optional[int] = None,
        exclude_txn_id: Optional[int] = None,
    ) -> list:
        """Expenses summed by category, month (``ym`` = 'YYYY-MM') and the
        paying account's currency, for ``date_from <= txn_date < date_until``.

        The end is exclusive so a date written with a time still falls inside
        its day. ``exclude_txn_id`` leaves one entry out (the one being edited).
        """
        sql = (
            "SELECT t.category_id AS category_id, substr(t.txn_date, 1, 7) AS ym, "
            "COALESCE(a.currency, 'INR') AS currency, SUM(t.amount) AS total "
            "FROM transactions t LEFT JOIN accounts a ON a.id = t.account_id "
            "WHERE t.txn_type = 'expense' AND t.txn_date >= ? AND t.txn_date < ?"
        )
        params: list = [date_from, date_until]
        if category_id is not None:
            sql += " AND t.category_id = ?"
            params.append(category_id)
        if exclude_txn_id is not None:
            sql += " AND t.id <> ?"
            params.append(exclude_txn_id)
        sql += " GROUP BY t.category_id, ym, COALESCE(a.currency, 'INR')"
        return self.db.fetch_all(sql, tuple(params))

    def distinct_years(self) -> list[str]:
        rows = self.db.fetch_all(
            "SELECT DISTINCT strftime('%Y', txn_date) AS y "
            "FROM transactions ORDER BY y DESC"
        )
        return [r["y"] for r in rows if r["y"]]

    def ledger_balances(self) -> dict[int, float]:
        """Ledger-implied balance per account (see services/ledger.py)."""
        totals: dict[int, float] = {}
        for r in self.db.fetch_all(
            f"SELECT account_id AS aid, SUM({_PRIMARY_EFFECT}) AS total "
            "FROM transactions GROUP BY account_id"
        ):
            totals[r["aid"]] = totals.get(r["aid"], 0.0) + float(r["total"] or 0.0)
        for r in self.db.fetch_all(
            "SELECT counter_account_id AS aid, SUM(amount) AS total FROM transactions "
            "WHERE txn_type = 'transfer' AND counter_account_id IS NOT NULL "
            "GROUP BY counter_account_id"
        ):
            totals[r["aid"]] = totals.get(r["aid"], 0.0) + float(r["total"] or 0.0)
        return totals

    def exists_with_tag(self, tag: str) -> bool:
        """True if any transaction carries ``tag`` in its comma-separated tags."""
        row = self.db.fetch_one(
            "SELECT 1 FROM transactions WHERE ',' || REPLACE(COALESCE(tags, ''), ' ', '') "
            "|| ',' LIKE ? LIMIT 1",
            (f"%,{tag},%",),
        )
        return row is not None

    def holding_cashflows(self, holding_id: Optional[int] = None) -> list:
        """Buy/sell rows linked to holdings: (holding_id, txn_date, txn_type, amount)."""
        sql = (
            "SELECT holding_id, txn_date, txn_type, amount FROM transactions "
            "WHERE holding_id IS NOT NULL "
            "AND txn_type IN ('investment_buy', 'investment_sell')"
        )
        params: tuple = ()
        if holding_id is not None:
            sql += " AND holding_id = ?"
            params = (holding_id,)
        return self.db.fetch_all(sql + " ORDER BY txn_date", params)
