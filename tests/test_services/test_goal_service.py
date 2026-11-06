"""Tests for GoalService: CRUD validation, holding links, funding sync."""
from __future__ import annotations

import pytest

from db.connection import Database
from models.goal import Goal
from models.holding import Holding
from repositories.goal_holding_repo import GoalHoldingRepository
from repositories.goal_repo import GoalRepository
from repositories.holding_repo import HoldingRepository
from services.goal_service import GoalService


def _service(db: Database) -> tuple[GoalService, HoldingRepository]:
    goal_repo = GoalRepository(db)
    link_repo = GoalHoldingRepository(db)
    holding_repo = HoldingRepository(db)
    return GoalService(goal_repo, link_repo, holding_repo), holding_repo


def test_create_goal_requires_name(temp_db: Database):
    svc, _ = _service(temp_db)
    with pytest.raises(ValueError):
        svc.create(Goal(name="  ", target_amount=100_000.0))


def test_create_goal_links_holdings_and_syncs_funding(temp_db: Database):
    svc, holding_repo = _service(temp_db)
    h1 = holding_repo.insert(Holding(name="SIP A", holding_type="sip",
                                      invested_amount=10_000.0, current_value=12_000.0))
    h2 = holding_repo.insert(Holding(name="SIP B", holding_type="sip",
                                      invested_amount=5_000.0, current_value=6_000.0))

    goal_id = svc.create(Goal(name="House", target_amount=1_000_000.0), holding_ids=[h1, h2])

    goal = svc.get(goal_id)
    assert goal is not None
    assert goal.current_amount == 18_000.0

    assert sorted(svc.linked_holding_ids(goal_id)) == sorted([h1, h2])
    assert set(svc.linked_holding_names(goal_id)) == {"SIP A", "SIP B"}


def test_refresh_all_linked_amounts(temp_db: Database):
    svc, holding_repo = _service(temp_db)
    h1 = holding_repo.insert(Holding(name="SIP A", holding_type="sip",
                                      invested_amount=10_000.0, current_value=12_000.0))

    goal_id = svc.create(Goal(name="Goal", target_amount=500_000.0), holding_ids=[h1])
    goal = svc.get(goal_id)
    assert goal.current_amount == 12_000.0

    # Holding value changes outside the goal; refresh should pick it up.
    holding = holding_repo.get_by_id(h1)
    holding.current_value = 20_000.0
    holding_repo.update(holding)

    goals = svc.list_all()
    svc.refresh_all_linked_amounts(goals)

    assert svc.get(goal_id).current_amount == 20_000.0


def test_toggle_paused_and_set_status(temp_db: Database):
    svc, _ = _service(temp_db)
    goal_id = svc.create(Goal(name="Emergency Fund", target_amount=300_000.0))
    goal = svc.get(goal_id)

    svc.toggle_paused(goal)
    assert goal.status == "paused"
    assert svc.get(goal_id).status == "paused"

    svc.toggle_paused(goal)
    assert goal.status == "active"

    svc.set_status(goal, "achieved")
    assert svc.get(goal_id).status == "achieved"


def test_update_requires_id_and_name(temp_db: Database):
    svc, _ = _service(temp_db)
    with pytest.raises(ValueError):
        svc.update(Goal(name="No id"))

    goal_id = svc.create(Goal(name="Goal", target_amount=100_000.0))
    goal = svc.get(goal_id)
    goal.name = "  "
    with pytest.raises(ValueError):
        svc.update(goal)


def test_delete_goal(temp_db: Database):
    svc, _ = _service(temp_db)
    goal_id = svc.create(Goal(name="Throwaway", target_amount=1.0))
    svc.delete(goal_id)
    assert svc.get(goal_id) is None


def test_holdings_for_dialog_and_required_sip(temp_db: Database):
    svc, holding_repo = _service(temp_db)
    holding_repo.insert(Holding(name="SIP A", holding_type="sip",
                                 invested_amount=1_000.0, current_value=1_200.0))

    options = svc.holdings_for_dialog()
    assert options[0][1] == "SIP A"

    goal = Goal(name="Future", target_amount=100_000.0, current_amount=0.0,
                 target_date="2030-01-01", expected_return=0.10)
    assert svc.required_sip(goal) > 0

    # No target date -> ProjectionService.required_sip_for_goal returns 0.
    no_date_goal = Goal(name="No Date", target_amount=100_000.0)
    assert svc.required_sip(no_date_goal) == 0.0
