"""Pure-function financial calculators. No side effects, no DB access."""
from __future__ import annotations

import math


def fv_of_lumpsum(principal: float, annual_rate: float, years: float) -> float:
    """Future value of a one-time investment."""
    return principal * ((1 + annual_rate) ** years)


def fv_of_sip(monthly_amount: float, annual_rate: float, years: float) -> float:
    """Future value of a monthly SIP paid at the **start** of each month.

    This is an annuity-due (the trailing ``* (1 + r)``): each instalment earns
    one extra month of return compared with end-of-month payments, which is how
    Indian SIPs debit in practice. :func:`required_monthly_sip` is its exact
    inverse - change one and you must change the other.
    """
    if monthly_amount <= 0 or years <= 0:
        return 0.0
    r = annual_rate / 12.0
    n = years * 12.0
    if abs(r) < 1e-9:
        return monthly_amount * n
    return monthly_amount * ((((1 + r) ** n) - 1) / r) * (1 + r)


def required_monthly_sip(target: float, annual_rate: float, years: float) -> float:
    """Monthly SIP (paid at the start of each month) needed to reach ``target``.

    Exact inverse of :func:`fv_of_sip` (annuity-due).
    """
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
    """Annualised internal rate of return for irregular cashflows.

    ``cashflows`` is a list of ``(days_from_t0, amount)``: money you put in is
    negative, money you get back (including today's value) is positive.

    Newton-Raphson from ``guess``; if that fails to converge, bisection over a
    bracket that is widened until the NPV changes sign.

    Raises ``ValueError`` when no rate exists (all flows the same sign) or none
    can be found - rather than returning an unconverged number.
    Returns ``0.0`` for an empty list.
    """
    if not cashflows:
        return 0.0
    if not any(cf > 0 for _, cf in cashflows) or not any(cf < 0 for _, cf in cashflows):
        raise ValueError("XIRR needs at least one negative and one positive cashflow")

    years = [(d / 365.0, cf) for d, cf in cashflows]

    def npv(rate: float) -> float:
        return sum(cf / ((1 + rate) ** t) for t, cf in years)

    def dnpv(rate: float) -> float:
        return sum(-t * cf / ((1 + rate) ** (t + 1)) for t, cf in years)

    # 1. Newton-Raphson
    rate = guess
    for _ in range(100):
        if rate <= -0.999999:
            break
        try:
            f = npv(rate)
            df = dnpv(rate)
        except (OverflowError, ZeroDivisionError):
            break
        if abs(f) < 1e-7:
            return rate
        if df == 0 or not math.isfinite(df):
            break
        new_rate = rate - f / df
        if not math.isfinite(new_rate):
            break
        if abs(new_rate - rate) < 1e-10:
            if new_rate > -0.999999 and abs(npv(new_rate)) < 1e-4 * max(1.0, max(abs(cf) for _, cf in years)):
                return new_rate
            break
        rate = new_rate

    # 2. Bisection fallback
    lo, hi = -0.999999, 1.0
    try:
        f_lo = npv(lo)
    except OverflowError:
        f_lo = math.inf
    f_hi = npv(hi)
    while f_lo * f_hi > 0 and hi < 1e6:
        hi *= 2
        try:
            f_hi = npv(hi)
        except OverflowError:
            break
    if not (math.isfinite(f_hi)) or f_lo * f_hi > 0:
        raise ValueError("XIRR did not converge for these cashflows")
    for _ in range(300):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-9 or (hi - lo) < 1e-12:
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2
