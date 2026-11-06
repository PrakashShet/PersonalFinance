"""Tests for ProjectionService: required SIP, retirement corpus/plan,
long-term projection, liability amortization, and goal forecasts.
"""
from __future__ import annotations

from models.goal import Goal
from models.liability import Liability
from repositories.goal_holding_repo import GoalHoldingRepository
import math

from services.projection_service import (
    Assumptions,
    Baseline,
    ProjectionService,
    Stress,
)


def _baseline(**overrides) -> Baseline:
    base = dict(
        net_worth=500_000.0,
        portfolio_value=500_000.0,
        cash_and_bank=100_000.0,
        liabilities_outstanding=0.0,
        monthly_net_income=80_000.0,
        monthly_gross_income=100_000.0,
        monthly_expenses=40_000.0,
        monthly_emi=0.0,
        monthly_sip=10_000.0,
        active_liabilities=[],
    )
    base.update(overrides)
    return Baseline(**base)


def test_required_sip_for_goal_with_target_date():
    svc = ProjectionService()
    goal = Goal(name="Vacation", target_amount=200_000.0, current_amount=20_000.0,
                 target_date="2030-01-01", expected_return=0.10)
    sip = svc.required_sip_for_goal(goal)
    assert sip > 0


def test_required_sip_for_goal_without_target_date_is_zero():
    svc = ProjectionService()
    goal = Goal(name="No date", target_amount=200_000.0)
    assert svc.required_sip_for_goal(goal) == 0.0


def test_retirement_corpus_needed_is_positive_and_scales_with_expenses():
    svc = ProjectionService()
    small = svc.retirement_corpus_needed(annual_expense_today=600_000.0, years_to_retirement=20)
    large = svc.retirement_corpus_needed(annual_expense_today=1_200_000.0, years_to_retirement=20)
    assert small > 0
    assert large > small


def test_project_long_term_basic():
    svc = ProjectionService()
    baseline = _baseline()
    assumptions = Assumptions(current_age=30, retirement_age=60, horizon_years=5)

    points = svc.project_long_term(baseline, assumptions)

    assert len(points) == 6  # years 0..5 inclusive
    assert points[0].year == 0
    assert points[0].portfolio_value == baseline.portfolio_value
    # Portfolio should grow over time given positive savings and returns.
    assert points[-1].portfolio_value > points[0].portfolio_value


def test_retirement_plan_basic():
    svc = ProjectionService()
    baseline = _baseline()
    assumptions = Assumptions(current_age=55, retirement_age=60, life_expectancy=85)

    plan = svc.retirement_plan(baseline, assumptions)

    assert plan.years_to_retirement == 5
    assert plan.corpus_needed > 0
    assert plan.corpus_projected >= baseline.portfolio_value
    assert isinstance(plan.on_track, bool)


def test_liability_amortization_pays_down_balance():
    svc = ProjectionService()
    liability = Liability(
        name="Personal Loan", liability_type="personal_loan",
        outstanding=100_000.0, interest_rate=12.0, emi_amount=9_000.0,
    )
    schedule = svc.liability_amortization(liability)

    assert len(schedule) >= 1
    # Balance should decrease (or be paid off) by the end of the schedule.
    assert schedule[-1][1] < liability.outstanding


def test_liability_amortization_handles_no_emi():
    svc = ProjectionService()
    liability = Liability(name="Revolving", liability_type="credit_card", outstanding=5_000.0)
    schedule = svc.liability_amortization(liability)
    # No EMI/rate info -> a single flat year with the same balance.
    assert schedule == [(1, 5_000.0, 0.0)]


def test_goal_forecasts(temp_db):
    svc = ProjectionService()
    gh_repo = GoalHoldingRepository(temp_db)

    goal = Goal(id=1, name="House", target_amount=1_000_000.0, current_amount=200_000.0,
                 target_date="2030-01-01", expected_return=0.10)

    forecasts = svc.goal_forecasts([goal], gh_repo, holdings_by_id={})

    assert len(forecasts) == 1
    forecast = forecasts[0]
    assert forecast.funded == 200_000.0
    assert forecast.target == 1_000_000.0
    assert forecast.required_sip > 0
    assert forecast.estimated_current_sip == 0.0


# --- drawdown: deficits are paid from cash, then the portfolio ---------------

def test_retiree_spends_down_portfolio_and_runs_out():
    """Rs 1 Cr, Rs 12 L/yr expenses growing 6%, no income: must deplete.
    Before the fix the portfolio compounded to ~Rs 10.8 Cr by 85."""
    svc = ProjectionService()
    baseline = _baseline(portfolio_value=10_000_000.0, cash_and_bank=0.0,
                         monthly_net_income=0.0, monthly_gross_income=0.0,
                         monthly_expenses=100_000.0, net_worth=10_000_000.0)
    a = Assumptions(current_age=60, retirement_age=60, horizon_years=25,
                    expected_return=0.10, post_retire_return=0.07)
    points = svc.project_long_term(baseline, a)

    assert points[-1].portfolio_value == 0.0
    age = svc.depletion_age(points)
    assert age is not None and 65 <= age <= 75
    assert all(p.contributions == 0.0 for p in points)
    assert any(p.withdrawals > 0 for p in points)
    # Year 1 grows at the post-retirement rate, then pays the year's deficit.
    expected_y1 = 10_000_000.0 * 1.07 - 1_200_000.0 * 1.06
    assert math.isclose(points[1].portfolio_value, expected_y1, rel_tol=1e-9)


def test_income_shock_draws_cash_before_portfolio():
    svc = ProjectionService()
    baseline = _baseline(cash_and_bank=600_000.0, monthly_expenses=40_000.0)
    a = Assumptions(current_age=30, retirement_age=60, horizon_years=3)
    shocked = svc.project_long_term(baseline, a, Stress(return_drop=0.0, income_shock_years=2))

    y1 = shocked[1]
    assert y1.net_income == 0.0
    assert y1.savings < 0
    assert y1.withdrawals > 0
    assert y1.cash < baseline.cash_and_bank          # cash spent first
    assert y1.portfolio_value == baseline.portfolio_value * 1.10


def test_working_years_still_accumulate():
    svc = ProjectionService()
    points = svc.project_long_term(_baseline(), Assumptions(current_age=30, horizon_years=5))
    assert all(p.shortfall == 0 for p in points)
    assert points[-1].portfolio_value > points[0].portfolio_value
    assert svc.depletion_age(points) is None
