"""Pure-function financial calculators. No side effects, no DB access."""
from __future__ import annotations

import math


def fv_of_lumpsum(principal: float, annual_rate: float, years: float) -> float:
    """Future value of a one-time investment."""
    return principal * ((1 + annual_rate) ** years)


def fv_of_sip(monthly_amount: float, annual_rate: float, years: float) -> float:
    """Future value of a monthly SIP (end-of-period payment)."""
    if monthly_amount <= 0 or years <= 0:
        return 0.0
    r = annual_rate / 12.0
    n = years * 12.0
    if abs(r) < 1e-9:
        return monthly_amount * n
    return monthly_amount * ((((1 + r) ** n) - 1) / r) * (1 + r)


def required_monthly_sip(target: float, annual_rate: float, years: float) -> float:
    """Monthly SIP needed to reach `target` in `years` at `annual_rate`."""
    if target <= 0 or years <= 0:
        return 0.0
    r = annual_rate / 12.0
    n = years * 12.0
    if abs(r) < 1e-9:
        return target / n
    return target * r / ((((1 + r) ** n) - 1) * (1 + r))


def emi(principal: float, annual_rate: float, tenure_months: int) -> float:
    """Standard EMI formula."""
    if principal <= 0 or tenure_months <= 0:
        return 0.0
    r = annual_rate / 12.0
    if abs(r) < 1e-9:
        return principal / tenure_months
    return principal * r * ((1 + r) ** tenure_months) / (((1 + r) ** tenure_months) - 1)


def xirr(cashflows: list[tuple[float, float]], guess: float = 0.1) -> float:
    """Extended IRR (cashflows: list of (days_from_t0, amount)).
    Returns annualized rate. Uses Newton-Raphson; falls back to bisection."""
    if not cashflows:
        return 0.0

    def npv(rate: float) -> float:
        return sum(cf / ((1 + rate) ** (d / 365.0)) for d, cf in cashflows)

    def dnpv(rate: float) -> float:
        return sum(-(d / 365.0) * cf / ((1 + rate) ** ((d / 365.0) + 1)) for d, cf in cashflows)

    rate = guess
    for _ in range(100):
        f = npv(rate)
        if abs(f) < 1e-6:
            return rate
        df = dnpv(rate)
        if abs(df) < 1e-12:
            break
        new_rate = rate - f / df
        if math.isnan(new_rate) or math.isinf(new_rate):
            break
        if abs(new_rate - rate) < 1e-7:
            return new_rate
        rate = new_rate
    return rate
