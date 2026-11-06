"""FX conversion in net worth: never add foreign money as if it were rupees."""
from __future__ import annotations

import pytest

from models.account import Account
from repositories.account_repo import AccountRepository
from repositories.holding_repo import HoldingRepository
from repositories.liability_repo import LiabilityRepository
from repositories.reference_repos import FxRateRepository
from services.fx_service import FxService
from services.net_worth_service import NetWorthService


def _wire(db):
    accounts = AccountRepository(db)
    fx = FxService(FxRateRepository(db))
    nw = NetWorthService(db, accounts, HoldingRepository(db), LiabilityRepository(db), fx_service=fx)
    return accounts, fx, nw


def test_foreign_balance_without_rate_is_reported_not_summed(temp_db):
    accounts, _fx, nw = _wire(temp_db)
    accounts.insert(Account(name="HDFC", account_type="savings", current_balance=100_000.0))
    accounts.insert(Account(name="Chase", account_type="savings", currency="USD", current_balance=1_000.0))

    bs = nw.compute()
    assert bs.cash_and_bank == 100_000.0
    assert bs.unconverted == {"USD": 1_000.0}


def test_foreign_balance_converted_with_rate(temp_db):
    accounts, fx, nw = _wire(temp_db)
    accounts.insert(Account(name="HDFC", account_type="savings", current_balance=100_000.0))
    accounts.insert(Account(name="Chase", account_type="savings", currency="USD", current_balance=1_000.0))
    fx.set_rate("usd", 83.5)

    bs = nw.compute()
    assert bs.cash_and_bank == 100_000.0 + 83_500.0
    assert bs.unconverted == {}
    assert fx.rate("INR") == 1.0


def test_invalid_rates_rejected(temp_db):
    _accounts, fx, _nw = _wire(temp_db)
    with pytest.raises(ValueError):
        fx.set_rate("USD", 0)
    with pytest.raises(ValueError):
        fx.set_rate("INR", 2.0)
