"""Sanity tests for financial calculators."""
from __future__ import annotations

import math

from utils.calculators import emi, fv_of_lumpsum, fv_of_sip, required_monthly_sip, xirr


def test_fv_lumpsum_zero_rate():
    assert fv_of_lumpsum(100000, 0, 10) == 100000


def test_fv_lumpsum_growth():
    # 1L @ 10% for 10y = 2.5937L
    assert math.isclose(fv_of_lumpsum(100000, 0.10, 10), 259374.25, rel_tol=1e-4)


def test_fv_sip():
    # 5000/m @ 12% for 10y -> ~ 11.6L
    val = fv_of_sip(5000, 0.12, 10)
    assert 1_100_000 < val < 1_200_000


def test_required_monthly_sip_roundtrip():
    target = 10_000_000
    sip = required_monthly_sip(target, 0.12, 20)
    fv = fv_of_sip(sip, 0.12, 20)
    assert math.isclose(fv, target, rel_tol=1e-4)


def test_emi():
    # 30L home loan @ 8.5% for 20y -> ~ 26,035
    assert math.isclose(emi(3_000_000, 0.085, 240), 26035, rel_tol=1e-3)


def test_xirr_simple():
    # -1L on day 0, +1.1L on day 365 -> 10%
    rate = xirr([(0, -100000), (365, 110000)])
    assert math.isclose(rate, 0.10, abs_tol=0.005)


# --- hand-checked values (docs/skills/verify-changes) ------------------------

def test_verify_changes_sanity_values():
    assert math.isclose(emi(3_820_000, 0.085, 240), 33_150.85, abs_tol=0.5)
    assert math.isclose(fv_of_sip(10_000, 0.12, 10), 2_323_390.76, abs_tol=1.0)
    assert math.isclose(xirr([(0, -100), (365, 110)]), 0.10, abs_tol=1e-6)


def test_xirr_raises_without_sign_change():
    import pytest

    with pytest.raises(ValueError):
        xirr([(0, 100), (365, 110)])
    with pytest.raises(ValueError):
        xirr([(0, -100), (365, -10)])


def test_xirr_multiple_flows_and_losses():
    # SIP-like: 12 monthly buys of 10k, worth 1.25L after a year (~ +8.8% XIRR... sign check)
    flows = [(30 * i, -10_000.0) for i in range(12)] + [(365, 125_000.0)]
    gain = xirr(flows)
    assert 0.05 < gain < 0.15
    # A 50% loss over two years is about -29% a year.
    loss = xirr([(0, -100_000.0), (730, 50_000.0)])
    assert math.isclose(loss, 0.5 ** 0.5 - 1, abs_tol=1e-4)


def test_xirr_falls_back_when_newton_starts_badly():
    # A guess far from the answer must still converge (bisection fallback).
    rate = xirr([(0, -1000.0), (365, 3000.0)], guess=50.0)
    assert math.isclose(rate, 2.0, abs_tol=1e-6)


# --- money formatting ----------------------------------------------------------

def test_fmt_inr_indian_grouping_and_sign():
    from utils.formatters import MINUS, fmt_inr, fmt_money

    assert fmt_inr(12345678) == "₹1,23,45,678.00"
    assert fmt_inr(-1234560) == f"{MINUS}₹12,34,560.00"
    assert fmt_inr(-1234560, compact=True) == f"{MINUS}₹12.35 L"
    assert fmt_inr(1234.5, decimals=0) == "₹1,234"
    assert fmt_inr(-0.004) == "₹0.00"            # no "minus zero"
    assert fmt_money(-1234.5, "USD") == f"{MINUS}$1,234.50"
