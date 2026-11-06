"""Labels and badge *tones* for entity types.

Badges carry a tone (neutral / accent / positive / negative / warning / info)
rather than a colour, so they follow the active theme. Type identity is the
text; the tone only signals meaning (e.g. a credit card debt reads as
"negative"), never a lookup the reader must memorise.
"""
from __future__ import annotations

FALLBACK_TONE = "neutral"

ACCOUNT_TYPE_LABELS = {
    "savings": "Savings",
    "current": "Current",
    "salary": "Salary",
    "cash": "Cash",
    "wallet": "Wallet",
    "credit_card": "Credit card",
}

INCOME_SOURCE_LABELS = {
    "salary": "Salary",
    "web_app": "SaaS / web app",
    "trading": "Trading",
    "rental": "Rental",
    "freelance": "Freelance",
    "dividend": "Dividend",
    "interest": "Interest",
    "other": "Other",
}

FREQ_LABELS = {
    "monthly": "Monthly",
    "quarterly": "Quarterly",
    "annual": "Yearly",
    "yearly": "Yearly",
    "irregular": "Irregular",
    "one_time": "One-time",
}

HOLDING_LABELS = {
    "stock": "Stock",
    "etf": "ETF",
    "sip": "SIP",
    "mutual_fund": "Mutual fund",
    "fd": "Fixed deposit",
    "ppf": "PPF",
    "epf": "EPF",
    "nps": "NPS",
    "bond": "Bond",
    "gold_coin": "Gold coin",
    "gold_jewelry": "Gold jewellery",
    "term_insurance": "Term insurance",
    "crypto": "Crypto",
    "real_estate": "Real estate",
}

LIABILITY_LABELS = {
    "home_loan": "Home loan",
    "car_loan": "Car loan",
    "personal_loan": "Personal loan",
    "education_loan": "Education loan",
    "credit_card": "Credit card",
    "bnpl": "Buy now, pay later",
}

GOAL_STATUS_TONE = {
    "active": "accent",
    "achieved": "positive",
    "paused": "warning",
    "abandoned": "neutral",
}

TXN_TYPE_LABELS = {
    "expense": "Expense",
    "income": "Income",
    "transfer": "Transfer",
    "investment_buy": "Invested",
    "investment_sell": "Withdrawn",
    "adjustment": "Adjustment",
}


def label(mapping: dict, key, default: str = "") -> str:
    if key is None:
        return default
    return mapping.get(key, str(key).replace("_", " ").title())
