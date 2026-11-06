"""Tests for LiabilityService: CRUD validation and aggregates."""
from __future__ import annotations

import pytest

from db.connection import Database
from models.liability import Liability
from repositories.liability_repo import LiabilityRepository
from services.liability_service import LiabilityService


def _service(db: Database) -> LiabilityService:
    return LiabilityService(LiabilityRepository(db))


def test_create_requires_name(temp_db: Database):
    svc = _service(temp_db)
    with pytest.raises(ValueError):
        svc.create(Liability(name="  ", liability_type="home_loan"))


def test_create_update_delete_and_toggle(temp_db: Database):
    svc = _service(temp_db)
    liability_id = svc.create(
        Liability(name="Car Loan", liability_type="car_loan", principal=500_000.0, outstanding=400_000.0)
    )

    liability = svc.get(liability_id)
    assert liability is not None

    liability.outstanding = 350_000.0
    svc.update(liability)
    assert svc.get(liability_id).outstanding == 350_000.0

    svc.toggle_active(liability)
    assert svc.get(liability_id).is_active == 0

    svc.delete(liability_id)
    assert svc.get(liability_id) is None


def test_update_requires_id_and_name(temp_db: Database):
    svc = _service(temp_db)
    with pytest.raises(ValueError):
        svc.update(Liability(name="No id", liability_type="car_loan"))

    liability_id = svc.create(Liability(name="Loan", liability_type="personal_loan", outstanding=1_000.0))
    liability = svc.get(liability_id)
    liability.name = ""
    with pytest.raises(ValueError):
        svc.update(liability)


def test_total_outstanding(temp_db: Database):
    svc = _service(temp_db)
    svc.create(Liability(name="Home Loan", liability_type="home_loan", outstanding=1_500_000.0))
    svc.create(Liability(name="Car Loan", liability_type="car_loan", outstanding=300_000.0))

    assert svc.total_outstanding() == 1_800_000.0
