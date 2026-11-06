"""Repository tests for the goal<->holding join table."""
from __future__ import annotations

from models.goal import Goal
from models.holding import Holding
from repositories.goal_holding_repo import GoalHoldingRepository
from repositories.goal_repo import GoalRepository
from repositories.holding_repo import HoldingRepository


def test_goal_holding_link_and_funded_amount(temp_db):
    holding_repo = HoldingRepository(temp_db)
    h1 = holding_repo.insert(Holding(name="SIP A", holding_type="sip",
                                      invested_amount=10_000.0, current_value=12_000.0))
    h2 = holding_repo.insert(Holding(name="SIP B", holding_type="sip",
                                      invested_amount=5_000.0, current_value=6_000.0))

    goal_repo = GoalRepository(temp_db)
    goal_id = goal_repo.insert(Goal(name="House Down Payment", target_amount=1_000_000.0))

    link_repo = GoalHoldingRepository(temp_db)
    link_repo.set_for_goal(goal_id, [h1, h2])

    ids = link_repo.holding_ids_for_goal(goal_id)
    assert sorted(ids) == sorted([h1, h2])
    assert link_repo.funded_amount(goal_id) == 12_000.0 + 6_000.0


def test_goal_holding_set_for_goal_replaces(temp_db):
    holding_repo = HoldingRepository(temp_db)
    h1 = holding_repo.insert(Holding(name="SIP A", holding_type="sip",
                                      invested_amount=10_000.0, current_value=12_000.0))
    h2 = holding_repo.insert(Holding(name="SIP B", holding_type="sip",
                                      invested_amount=5_000.0, current_value=6_000.0))

    goal_repo = GoalRepository(temp_db)
    goal_id = goal_repo.insert(Goal(name="Goal", target_amount=100_000.0))

    link_repo = GoalHoldingRepository(temp_db)
    link_repo.set_for_goal(goal_id, [h1])
    assert link_repo.holding_ids_for_goal(goal_id) == [h1]

    link_repo.set_for_goal(goal_id, [h2])
    assert link_repo.holding_ids_for_goal(goal_id) == [h2]
