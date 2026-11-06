"""Display formatters - Indian numbering (lakh / crore), currency, percent.

Negative amounts put the sign before the symbol: "−₹12,34,500.00", not
"₹-12,34,500.00". The sign is a true minus (U+2212) for display.
"""
from __future__ import annotations

from datetime import datetime

MINUS = "−"

CURRENCY_SYMBOLS: dict[str, str] = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "AED": "AED ",
}


def fmt_money(amount: float, currency: str = "INR", compact: bool = False,
              decimals: int = 2) -> str:
    """Currency-aware money formatter.

    INR uses Indian lakh/crore grouping (via fmt_inr); other currencies use
    Western thousands grouping with K/M/B compaction. Falls back to showing the
    raw currency code as a prefix for unknown currencies.
    """
    if amount is None:
        return "—"
    if (currency or "INR") == "INR":
        return fmt_inr(amount, compact=compact, decimals=decimals)
    sym = CURRENCY_SYMBOLS.get(currency, f"{currency} ")
    sign = MINUS if round(amount, max(decimals, 2)) < 0 else ""
    a = abs(amount)
    if compact:
        if a >= 1e9:
            return f"{sign}{sym}{a / 1e9:.2f}B"
        if a >= 1e6:
            return f"{sign}{sym}{a / 1e6:.2f}M"
        if a >= 1e3:
            return f"{sign}{sym}{a / 1e3:.1f}K"
    return f"{sign}{sym}{a:,.{decimals}f}"


def _indian_group(whole: str) -> str:
    """'1234567' -> '12,34,567' (last three digits, then pairs)."""
    if len(whole) <= 3:
        return whole
    last3, rest = whole[-3:], whole[:-3]
    chunks = []
    while len(rest) > 2:
        chunks.append(rest[-2:])
        rest = rest[:-2]
    if rest:
        chunks.append(rest)
    return ",".join(reversed(chunks)) + "," + last3


def fmt_inr(amount: float, compact: bool = False, decimals: int = 2) -> str:
    """Format as ₹ with Indian comma grouping (e.g. ₹12,34,567.00).
    If ``compact``, shorten to K / L / Cr."""
    if amount is None:
        return "—"
    sign = MINUS if round(amount, max(decimals, 2)) < 0 else ""
    a = abs(amount)
    if compact:
        if a >= 1e7:
            return f"{sign}₹{a / 1e7:.2f} Cr"
        if a >= 1e5:
            return f"{sign}₹{a / 1e5:.2f} L"
        if a >= 1e3:
            return f"{sign}₹{a / 1e3:.1f} K"
    text = f"{a:.{decimals}f}"
    whole, _, frac = text.partition(".")
    grouped = _indian_group(whole)
    return f"{sign}₹{grouped}" + (f".{frac}" if frac else "")


def fmt_pct(value: float, decimals: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{decimals}f}%"


def fmt_date(date_str: str, fmt: str = "%d %b %Y") -> str:
    if not date_str:
        return "—"
    try:
        return datetime.fromisoformat(date_str).strftime(fmt)
    except Exception:
        return date_str
