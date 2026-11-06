"""Long-range personal-finance projection.

Five pillars:
  1. Net-worth trajectory   — portfolio growth + contributions − liabilities paid.
  2. Annual cashflow        — income (with salary growth) vs expenses (inflated)
                              vs EMIs vs savings vs contributions, year by year.
  3. Retirement readiness   — corpus needed at retirement, corpus projected on
                              the current path, gap, and additional SIP needed.
  4. Per-goal feasibility   — for each active goal, the on-track completion
                              date given current funding & investments.
  5. Liability payoff       — amortization schedule per loan.

All five share a single ``Baseline`` (auto-derived from the live data) plus a
single ``Assumptions`` object (rates, ages, growth) so changing an assumption
re-flows the whole picture. A ``Stress`` overlay reruns the projection with
adverse inputs so you can compare baseline vs adversity.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date
from typing import Optional

from models.goal import Goal
from utils.calculators import (
    emi as calc_emi,
    fv_of_lumpsum,
    required_monthly_sip,
)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Assumptions:
    current_age: int = 30
    retirement_age: int = 60
    life_expectancy: int = 85
    horizon_years: int = 30          # how far to project (defaults near retirement)
    expected_return: float = 0.10    # pre-retirement portfolio return (annual)
    post_retire_return: float = 0.07 # post-retirement, more conservative
    inflation: float = 0.06
    salary_growth: float = 0.08
    expense_growth: float = 0.06
    withdrawal_rate: float = 0.04    # 4% safe withdrawal


@dataclass
class Stress:
    label: str = "Adverse"
    return_drop: float = 0.03        # percentage points off expected_return
    income_shock_years: int = 1      # zero net income for first N years
    expense_spike: float = 0.0       # one-time bump to base expenses (pct)


@dataclass
class Baseline:
    net_worth: float
    portfolio_value: float
    cash_and_bank: float
    liabilities_outstanding: float
    monthly_net_income: float        # take-home
    monthly_gross_income: float
    monthly_expenses: float          # derived from recent transactions (or 0)
    monthly_emi: float               # current EMI outflow
    monthly_sip: float               # current SIP contributions
    active_liabilities: list = field(default_factory=list)


@dataclass
class YearPoint:
    year: int                        # 0 = today
    age: int
    gross_income: float              # annual
    net_income: float                # annual (take-home)
    expenses: float                  # annual
    emi_outflow: float               # annual
    savings: float                   # annual net_income - expenses - emi; NEGATIVE = deficit
    contributions: float             # annual amount fed into the portfolio
    portfolio_value: float
    liabilities_outstanding: float
    net_worth_nominal: float
    net_worth_real: float            # in today's rupees
    withdrawals: float = 0.0         # deficit paid from cash + portfolio this year
    shortfall: float = 0.0           # deficit nothing was left to pay for
    cash: float = 0.0                # cash & bank at year end


@dataclass
class RetirementPlan:
    years_to_retirement: int
    annual_expenses_today: float
    annual_expenses_at_retirement: float
    corpus_needed: float
    corpus_projected: float
    gap: float
    required_additional_sip: float
    on_track: bool


@dataclass
class GoalForecast:
    goal: Goal
    funded: float
    target: float
    target_date: Optional[str]
    months_to_target: Optional[int]
    required_sip: float              # to hit target by target_date
    estimated_current_sip: float     # from linked holdings' sip_amount
    on_track_months: Optional[int]   # months until goal achieved at current SIP
    on_track_date: Optional[str]
    will_meet_target: bool


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ProjectionService:

    # ── existing API kept for goals_view / dashboard ──────────────────────
    def required_sip_for_goal(self, goal: Goal) -> float:
        if not goal.target_date:
            return 0.0
        try:
            target = date.fromisoformat(goal.target_date)
        except ValueError:
            return 0.0
        months = max(1, (target.year - date.today().year) * 12
                     + (target.month - date.today().month))
        gap = max(0.0, goal.target_amount - goal.current_amount)
        return required_monthly_sip(gap, goal.expected_return, months / 12)

    def retirement_corpus_needed(
        self,
        annual_expense_today: float,
        years_to_retirement: int,
        years_in_retirement: int = 30,
        inflation: float = 0.06,
        post_retire_return: float = 0.07,
    ) -> float:
        future_annual = annual_expense_today * ((1 + inflation) ** years_to_retirement)
        real_return = (1 + post_retire_return) / (1 + inflation) - 1
        if abs(real_return) < 1e-6:
            return future_annual * years_in_retirement
        return future_annual * (1 - (1 + real_return) ** -years_in_retirement) / real_return

    # ── auto-derive baseline from live data ───────────────────────────────
    @staticmethod
    def derive_baseline(
        net_worth_svc,
        holding_repo,
        liability_repo,
        income_repo,
        income_svc,
        txn_service,
        months_for_expense_avg: int = 6,
    ) -> Baseline:
        bs = net_worth_svc.compute()
        holdings = holding_repo.list_active()
        liabs = liability_repo.list_active()
        sources = income_repo.list_active()

        # Monthly SIP from active sip holdings
        sip = sum((h.sip_amount or 0.0) for h in holdings if h.sip_amount)

        # Current EMI outflow from amortizable loans
        emi_total = 0.0
        for lb in liabs:
            emi_val = lb.emi_amount or (
                calc_emi(lb.outstanding, (lb.interest_rate or 0) / 100, lb.remaining_months)
                if lb.remaining_months and lb.interest_rate else 0
            )
            emi_total += emi_val

        gross_income = sum(income_svc.gross_monthly(s) for s in sources if s.is_active)
        net_income = sum(income_svc.net_monthly(s) for s in sources if s.is_active)

        # Recent monthly expense average from the ledger. EMIs logged from the
        # Dashboard (tagged "emi:") are excluded - loan payments are projected
        # separately from the amortisation schedule, and counting them in both
        # places would double the outflow.
        today = date.today()
        totals = []
        for i in range(months_for_expense_avg):
            month_index = today.year * 12 + (today.month - 1) - i
            y, m = divmod(month_index, 12)
            expense = txn_service.monthly_expense(str(y), f"{m + 1:02d}", exclude_emi=True)
            if expense > 0:
                totals.append(expense)
        avg_expense = sum(totals) / len(totals) if totals else 0.0

        return Baseline(
            net_worth=bs.net_worth,
            portfolio_value=bs.investments,
            cash_and_bank=bs.cash_and_bank,
            liabilities_outstanding=bs.total_liabilities,
            monthly_net_income=net_income,
            monthly_gross_income=gross_income,
            monthly_expenses=avg_expense,
            monthly_emi=emi_total,
            monthly_sip=sip,
            active_liabilities=list(liabs),
        )

    # ── year-by-year projection ───────────────────────────────────────────
    def project_long_term(
        self,
        baseline: Baseline,
        assumptions: Assumptions,
        stress: Optional[Stress] = None,
    ) -> list[YearPoint]:
        """Year-by-year cashflow and net worth.

        Each year: surplus (take-home - expenses - EMIs) is invested; a
        **deficit is paid from cash first, then by selling from the
        portfolio**. Once both are exhausted the unpaid part is reported as
        ``shortfall`` - see :meth:`depletion_age`. The portfolio grows at
        ``expected_return`` before retirement and ``post_retire_return`` after
        (both reduced by a stress ``return_drop``).

        Before 1.0 a deficit was floored at zero, so retirement and job-loss
        years never touched the portfolio and it compounded untouched forever.
        """
        a = assumptions
        drop = stress.return_drop if stress else 0.0
        income_shock = stress.income_shock_years if stress else 0
        expense_spike = (stress.expense_spike if stress else 0.0)

        years = max(1, a.horizon_years)
        portfolio = baseline.portfolio_value
        cash = max(0.0, baseline.cash_and_bank)
        # Build a yearly liability-outstanding series via amortization
        liab_series = self._aggregate_liability_balances(baseline.active_liabilities, years)
        emi_series = self._aggregate_emi_outflow(baseline.active_liabilities, years)

        base_expenses_annual = baseline.monthly_expenses * 12 * (1 + expense_spike)
        base_net_income_annual = baseline.monthly_net_income * 12
        base_gross_income_annual = baseline.monthly_gross_income * 12

        out: list[YearPoint] = []
        for y in range(years + 1):
            age = a.current_age + y
            growth_inc = (1 + a.salary_growth) ** y
            growth_exp = (1 + a.expense_growth) ** y

            retired = age >= a.retirement_age
            gross = 0.0 if retired else base_gross_income_annual * growth_inc
            net   = 0.0 if retired else base_net_income_annual   * growth_inc
            if y < income_shock:
                gross = 0.0
                net = 0.0

            expenses = base_expenses_annual * growth_exp
            emi_y = emi_series[y] if y < len(emi_series) else 0.0
            savings = net - expenses - emi_y

            contributions = withdrawals = shortfall = 0.0
            # Year 0 is today: report the cashflow, move no money.
            if y > 0:
                rate = (a.post_retire_return if retired else a.expected_return) - drop
                portfolio = portfolio * (1 + rate)
                if savings >= 0:
                    contributions = savings
                    portfolio += contributions
                else:
                    need = -savings
                    from_cash = min(cash, need)
                    cash -= from_cash
                    need -= from_cash
                    from_portfolio = min(portfolio, need)
                    portfolio -= from_portfolio
                    need -= from_portfolio
                    withdrawals = from_cash + from_portfolio
                    shortfall = need

            liab_out = liab_series[y] if y < len(liab_series) else 0.0
            net_worth = portfolio + cash - liab_out
            real = net_worth / ((1 + a.inflation) ** y) if y else net_worth

            out.append(YearPoint(
                year=y, age=age,
                gross_income=gross, net_income=net,
                expenses=expenses, emi_outflow=emi_y,
                savings=savings, contributions=contributions,
                portfolio_value=portfolio,
                liabilities_outstanding=liab_out,
                net_worth_nominal=net_worth, net_worth_real=real,
                withdrawals=withdrawals, shortfall=shortfall, cash=cash,
            ))
        return out

    @staticmethod
    def depletion_age(points: list[YearPoint]) -> Optional[int]:
        """First age at which expenses can no longer be paid, or None."""
        for p in points:
            if p.shortfall > 0.5:
                return p.age
        return None

    # ── retirement plan ───────────────────────────────────────────────────
    def retirement_plan(
        self, baseline: Baseline, assumptions: Assumptions
    ) -> RetirementPlan:
        a = assumptions
        years_to_retire = max(0, a.retirement_age - a.current_age)
        years_in_retire = max(1, a.life_expectancy - a.retirement_age)
        annual_today = baseline.monthly_expenses * 12
        corpus_needed = self.retirement_corpus_needed(
            annual_today, years_to_retire, years_in_retire,
            a.inflation, a.post_retire_return,
        )
        # Project to retirement to estimate the projected corpus
        proj = self.project_long_term(
            baseline, replace(a, horizon_years=years_to_retire) if years_to_retire else a
        )
        idx = min(years_to_retire, len(proj) - 1)
        corpus_projected = proj[idx].portfolio_value
        gap = max(0.0, corpus_needed - corpus_projected)
        req_sip = (
            required_monthly_sip(gap, a.expected_return, years_to_retire)
            if years_to_retire > 0 else 0.0
        )
        return RetirementPlan(
            years_to_retirement=years_to_retire,
            annual_expenses_today=annual_today,
            annual_expenses_at_retirement=annual_today * ((1 + a.inflation) ** years_to_retire),
            corpus_needed=corpus_needed,
            corpus_projected=corpus_projected,
            gap=gap,
            required_additional_sip=req_sip,
            on_track=corpus_projected >= corpus_needed,
        )

    # ── per-goal feasibility ──────────────────────────────────────────────
    def goal_forecasts(
        self,
        goals: list[Goal],
        gh_repo,
        holdings_by_id: dict,
    ) -> list[GoalForecast]:
        out: list[GoalForecast] = []
        today = date.today()
        for g in goals:
            funded = g.current_amount or 0.0
            target = g.target_amount or 0.0
            months_to_target: Optional[int] = None
            if g.target_date:
                try:
                    td = date.fromisoformat(g.target_date)
                    months_to_target = max(1, (td.year - today.year) * 12 + (td.month - today.month))
                except ValueError:
                    pass
            gap = max(0.0, target - funded)
            req_sip = (
                required_monthly_sip(gap, g.expected_return or 0.10, (months_to_target or 12) / 12)
                if months_to_target else 0.0
            )
            # Sum SIP from linked holdings
            ids = gh_repo.holding_ids_for_goal(g.id) if hasattr(gh_repo, "holding_ids_for_goal") else []
            est_sip = sum(
                (holdings_by_id[i].sip_amount or 0.0)
                for i in ids
                if i in holdings_by_id and holdings_by_id[i].sip_amount
            )
            on_track_m = self._months_to_target(funded, est_sip, g.expected_return or 0.10, target) if est_sip > 0 else None
            on_track_d: Optional[str] = None
            if on_track_m is not None:
                yr = today.year + (today.month - 1 + on_track_m) // 12
                mo = (today.month - 1 + on_track_m) % 12 + 1
                on_track_d = f"{yr}-{mo:02d}-01"
            will_meet = (
                on_track_m is not None and months_to_target is not None
                and on_track_m <= months_to_target
            )
            out.append(GoalForecast(
                goal=g, funded=funded, target=target,
                target_date=g.target_date,
                months_to_target=months_to_target,
                required_sip=req_sip,
                estimated_current_sip=est_sip,
                on_track_months=on_track_m,
                on_track_date=on_track_d,
                will_meet_target=will_meet,
            ))
        return out

    # ── liability amortization (per loan) ─────────────────────────────────
    def liability_amortization(self, liability) -> list[tuple[int, float, float]]:
        """Return [(year, balance_end, interest_paid_this_year), ...] until paid."""
        bal = float(liability.outstanding or 0.0)
        rate = float(liability.interest_rate or 0.0) / 100.0
        emi = float(
            liability.emi_amount
            or (calc_emi(bal, rate, liability.remaining_months)
                if (liability.remaining_months and rate) else 0.0)
        )
        if bal <= 0 or emi <= 0 or rate < 0:
            # Revolving / no EMI: report a single flat year
            return [(1, bal, 0.0)]
        monthly_rate = rate / 12.0
        out: list[tuple[int, float, float]] = []
        year_interest = 0.0
        months = 0
        while bal > 0.005 and months < 12 * 60:  # safety cap 60 yrs
            months += 1
            interest = bal * monthly_rate
            principal = min(bal, emi - interest)
            if principal <= 0:
                # EMI doesn't even cover interest — break to avoid infinite loop
                break
            bal -= principal
            year_interest += interest
            if months % 12 == 0 or bal <= 0.005:
                out.append((months // 12 + (1 if months % 12 else 0), max(0.0, bal), year_interest))
                year_interest = 0.0
        return out

    # ── internals ─────────────────────────────────────────────────────────
    def _aggregate_liability_balances(self, liabs: list, horizon_years: int) -> list[float]:
        """Total outstanding across all liabilities for each year-end 0..horizon."""
        schedules = [self._padded_schedule(lb, horizon_years) for lb in liabs]
        series: list[float] = []
        for y in range(horizon_years + 1):
            series.append(sum(sched.get(y, 0.0) for sched in schedules))
        return series

    def _padded_schedule(self, liability, horizon_years: int) -> dict[int, float]:
        sched = {0: float(liability.outstanding or 0.0)}
        for year, bal, _ in self.liability_amortization(liability):
            sched[year] = bal
        # carry-forward to the end of the horizon
        last_known = sched[0]
        for y in range(1, horizon_years + 1):
            if y in sched:
                last_known = sched[y]
            else:
                sched[y] = last_known
        return sched

    def _aggregate_emi_outflow(self, liabs: list, horizon_years: int) -> list[float]:
        """Total EMI outflow per year — stops contributing when a loan is paid."""
        out = [0.0] * (horizon_years + 1)
        for lb in liabs:
            rate = float(lb.interest_rate or 0.0) / 100.0
            emi = float(
                lb.emi_amount
                or (calc_emi(lb.outstanding, rate, lb.remaining_months)
                    if (lb.remaining_months and rate) else 0.0)
            )
            if emi <= 0:
                continue
            sched = self._padded_schedule(lb, horizon_years)
            for y in range(0, horizon_years + 1):
                # If still owing at year y end, EMI was paid during year y+1.
                if y < horizon_years and sched.get(y, 0.0) > 0.005:
                    out[y + 1] += emi * 12  # paid during year y+1
        return out

    @staticmethod
    def _months_to_target(funded: float, sip: float, annual_rate: float, target: float) -> Optional[int]:
        """Binary-search months t such that FV(funded, sip, t) >= target."""
        if sip <= 0 or target <= funded:
            return 0 if target <= funded else None
        r = annual_rate / 12.0
        lo, hi = 1, 12 * 60
        def fv(t):
            lump = fv_of_lumpsum(funded, annual_rate, t / 12.0)
            if abs(r) < 1e-9:
                annuity = sip * t
            else:
                annuity = sip * ((((1 + r) ** t) - 1) / r) * (1 + r)
            return lump + annuity
        if fv(hi) < target:
            return None
        while lo < hi:
            mid = (lo + hi) // 2
            if fv(mid) >= target:
                hi = mid
            else:
                lo = mid + 1
        return lo
