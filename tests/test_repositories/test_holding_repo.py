"""Repository CRUD smoke tests for holdings."""
from __future__ import annotations

from models.holding import Holding
from repositories.holding_repo import HoldingRepository


def test_holding_repo_insert_and_fetch(temp_db):
    repo = HoldingRepository(temp_db)
    holding_id = repo.insert(
        Holding(name="Nifty Index Fund", holding_type="mutual_fund",
                invested_amount=10_000.0, current_value=12_000.0)
    )
    row = repo.get_by_id(holding_id)
    assert row is not None
    assert row.name == "Nifty Index Fund"
    assert row.current_value == 12_000.0


def test_holding_repo_list_active_and_by_type(temp_db):
    repo = HoldingRepository(temp_db)
    repo.insert(Holding(name="HDFC Stock", holding_type="stock",
                         invested_amount=5_000.0, current_value=6_000.0, is_active=1))
    repo.insert(Holding(name="Old FD", holding_type="fd",
                         invested_amount=10_000.0, current_value=10_500.0, is_active=0))

    active = repo.list_active()
    assert len(active) == 1
    assert active[0].name == "HDFC Stock"

    stocks = repo.list_by_type("stock")
    assert len(stocks) == 1
    assert stocks[0].name == "HDFC Stock"


def test_holding_repo_totals(temp_db):
    repo = HoldingRepository(temp_db)
    repo.insert(Holding(name="A", holding_type="sip", invested_amount=1_000.0, current_value=1_200.0))
    repo.insert(Holding(name="B", holding_type="fd", invested_amount=2_000.0, current_value=2_100.0))

    assert repo.total_invested() == 3_000.0
    assert repo.total_current_value() == 3_300.0
