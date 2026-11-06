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
