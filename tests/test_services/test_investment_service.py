"""Tests for InvestmentService: amount normalization, allocation, breakdowns."""
from __future__ import annotations

import pytest

from db.connection import Database
from models.holding import Holding
from repositories.holding_repo import HoldingRepository
from services.investment_service import InvestmentService


def _service(db: Database) -> InvestmentService:
    return InvestmentService(HoldingRepository(db))


def test_add_holding_normalizes_amounts_from_quantity_and_price(temp_db: Database):
    svc = _service(temp_db)
    holding_id = svc.add_holding(
        Holding(name="Reliance", holding_type="stock", quantity=10,
                avg_price=2_000.0, current_price=2_500.0)
    )
    holding = svc.get(holding_id)
    assert holding.invested_amount == 20_000.0
    assert holding.current_value == 25_000.0


def test_add_holding_keeps_explicit_amounts(temp_db: Database):
    svc = _service(temp_db)
    holding_id = svc.add_holding(
        Holding(name="Gold ETF", holding_type="etf", quantity=5,
                avg_price=100.0, current_price=120.0,
                invested_amount=999.0, current_value=1_111.0)
    )
    holding = svc.get(holding_id)
    # Explicit amounts are not overwritten when already set.
    assert holding.invested_amount == 999.0
    assert holding.current_value == 1_111.0


def test_update_holding_requires_id(temp_db: Database):
    svc = _service(temp_db)
    with pytest.raises(ValueError):
        svc.update_holding(Holding(name="No id", holding_type="fd"))


def test_toggle_active_and_delete(temp_db: Database):
    svc = _service(temp_db)
    holding_id = svc.add_holding(
        Holding(name="FD", holding_type="fd", invested_amount=10_000.0, current_value=10_000.0)
    )
    holding = svc.get(holding_id)

    svc.toggle_active(holding)
    assert svc.get(holding_id).is_active == 0

    svc.delete_holding(holding_id)
    assert svc.get(holding_id) is None


def test_asset_allocation_buckets(temp_db: Database):
    svc = _service(temp_db)
    svc.add_holding(Holding(name="SIP A", holding_type="sip",
                             invested_amount=10_000.0, current_value=12_000.0))
    svc.add_holding(Holding(name="FD A", holding_type="fd",
                             invested_amount=50_000.0, current_value=52_000.0))
    svc.add_holding(Holding(name="Gold Coin", holding_type="gold_coin",
                             invested_amount=20_000.0, current_value=22_000.0))

    allocation = svc.asset_allocation()
    assert allocation["equity"] == 12_000.0
    assert allocation["debt"] == 52_000.0
    assert allocation["gold"] == 22_000.0


def test_stock_breakdown_by_cap(temp_db: Database):
    svc = _service(temp_db)
    svc.add_holding(Holding(name="Big Co", holding_type="stock", market_cap="large_cap",
                             invested_amount=10_000.0, current_value=15_000.0))
    svc.add_holding(Holding(name="Small Co", holding_type="stock", market_cap="small_cap",
                             invested_amount=5_000.0, current_value=4_000.0))
    svc.add_holding(Holding(name="Unclassified Co", holding_type="stock",
                             invested_amount=1_000.0, current_value=1_000.0))

    breakdown = svc.stock_breakdown_by_cap()
    assert breakdown["large_cap"] == 15_000.0
    assert breakdown["small_cap"] == 4_000.0
    assert breakdown["unclassified"] == 1_000.0


def test_upcoming_maturities(temp_db: Database):
    svc = _service(temp_db)
    svc.add_holding(Holding(name="Maturing FD", holding_type="fd",
                             invested_amount=10_000.0, current_value=10_500.0,
                             maturity_date="2026-06-15"))
    svc.add_holding(Holding(name="Far FD", holding_type="fd",
                             invested_amount=10_000.0, current_value=10_500.0,
                             maturity_date="2030-01-01"))

    due_soon = svc.upcoming_maturities(within_days=30)
    names = [h.name for h in due_soon]
    assert "Maturing FD" in names
    assert "Far FD" not in names
