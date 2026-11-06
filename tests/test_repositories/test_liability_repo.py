"""Repository CRUD smoke tests for liabilities."""
from __future__ import annotations

from models.liability import Liability
from repositories.liability_repo import LiabilityRepository


def test_liability_repo_insert_and_fetch(temp_db):
    repo = LiabilityRepository(temp_db)
    liability_id = repo.insert(
        Liability(name="Home Loan", liability_type="home_loan",
                  principal=2_000_000.0, outstanding=1_800_000.0)
    )
    row = repo.get_by_id(liability_id)
    assert row is not None
    assert row.name == "Home Loan"
    assert row.outstanding == 1_800_000.0


def test_liability_repo_list_active_and_total(temp_db):
    repo = LiabilityRepository(temp_db)
    repo.insert(Liability(name="Car Loan", liability_type="car_loan",
                          principal=500_000.0, outstanding=300_000.0, is_active=1))
    repo.insert(Liability(name="Closed Loan", liability_type="personal_loan",
                          principal=100_000.0, outstanding=0.0, is_active=0))

    active = repo.list_active()
    assert len(active) == 1
    assert active[0].name == "Car Loan"
    assert repo.total_outstanding() == 300_000.0
