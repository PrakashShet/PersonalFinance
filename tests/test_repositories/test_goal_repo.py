"""Repository CRUD smoke tests for goals."""
from __future__ import annotations

from models.goal import Goal
from repositories.goal_repo import GoalRepository


def test_goal_repo_insert_and_list(temp_db):
    repo = GoalRepository(temp_db)
    repo.insert(Goal(name="Retirement", target_amount=10_000_000.0, status="active"))
    repo.insert(Goal(name="Old Car Goal", target_amount=500_000.0, status="achieved"))

    all_goals = repo.list_all()
    assert len(all_goals) == 2

    active = repo.list_active()
    assert len(active) == 1
    assert active[0].name == "Retirement"


def test_goal_repo_update(temp_db):
    repo = GoalRepository(temp_db)
    goal_id = repo.insert(Goal(name="Vacation", target_amount=200_000.0, current_amount=0.0))

    goal = repo.get_by_id(goal_id)
    goal.current_amount = 50_000.0
    repo.update(goal)

    assert repo.get_by_id(goal_id).current_amount == 50_000.0
