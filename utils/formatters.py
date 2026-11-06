"""Display formatters — Indian numbering (lakh / crore), currency, percent."""
from __future__ import annotations

from datetime import datetime


CURRENCY_SYMBOLS: dict[str, str] = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "AED": "AED ",
}


def fmt_money(amount: float, currency: str = "INR", compact: bool = False) -> str:
    """Currency-aware money formatter.

    INR uses Indian lakh/crore grouping (via fmt_inr); other currencies use
    Western thousands grouping with K/M/B compaction. Falls back to showing the
    raw currency code as a prefix for unknown currencies.
    """
    if amount is None:
        return "—"
    if (currency or "INR") == "INR":
        return fmt_inr(amount, compact=compact)
    sym = CURRENCY_SYMBOLS.get(currency, f"{currency} ")
    if compact:
        a = abs(amount)
        if a >= 1e9:
            return f"{sym}{amount / 1e9:.2f}B"
        if a >= 1e6:
            return f"{sym}{amount / 1e6:.2f}M"
        if a >= 1e3:
            return f"{sym}{amount / 1e3:.1f}K"
    return f"{sym}{amount:,.2f}"


def fmt_inr(amount: float, compact: bool = False) -> str:
    """Format as ₹ with Indian comma grouping (e.g. 12,34,567).
    If `compact`, shorten to L / Cr."""
    if amount is None:
        return "—"
    if compact:
        if abs(amount) >= 1e7:
            return f"₹{amount / 1e7:.2f} Cr"
        if abs(amount) >= 1e5:
            return f"₹{amount / 1e5:.2f} L"
        if abs(amount) >= 1e3:
            return f"₹{amount / 1e3:.1f} K"
    # Indian numbering: last 3 digits then groups of 2
    s = f"{amount:,.2f}"  # English grouping first
    # Convert "1,234,567.89" -> "12,34,567.89"
    if "," in s:
        whole, _, frac = s.partition(".")
        whole = whole.replace(",", "")
        sign = ""
        if whole.startswith("-"):
            sign, whole = "-", whole[1:]
        if len(whole) > 3:
            last3 = whole[-3:]
            rest = whole[:-3]
            # split `rest` into 2-digit groups from the right
            chunks = []
            while len(rest) > 2:
                chunks.append(rest[-2:])
                rest = rest[:-2]
            if rest:
                chunks.append(rest)
            grouped = ",".join(reversed(chunks)) + "," + last3
            s = f"{sign}{grouped}.{frac}"
    return f"₹{s}"


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
