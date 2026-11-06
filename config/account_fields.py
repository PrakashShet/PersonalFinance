"""Canonical field metadata for the extended account detail sections.

Single source of truth used by:
  * the Account dataclass (field names mirror these attrs),
  * db/migrate.py (additive columns + their SQLite types),
  * the section edit dialog (form widgets) and details dialog (read-only view).

Keeping it in one place means the model, the database, and the UI cannot drift
apart.
"""
from __future__ import annotations

from dataclasses import dataclass

from config.constants import AccountType, LiabilityType


@dataclass(frozen=True)
class Field:
    attr: str
    label: str
    kind: str          # text|multiline|money|percent|int|day|combo|checkbox
    sqltype: str       # TEXT|REAL|INTEGER
    options: tuple = ()      # for combo: tuple of (value, label)
    required: bool = False
    placeholder: str = ""


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    fields: tuple


# ---- option lists ---------------------------------------------------------
_ACCOUNT_TYPES = (
    (AccountType.SAVINGS.value, "Savings"),
    (AccountType.CURRENT.value, "Current"),
    (AccountType.SALARY.value, "Salary"),
    (AccountType.CASH.value, "Cash"),
    (AccountType.WALLET.value, "Wallet"),
    (AccountType.CREDIT_CARD.value, "Credit Card"),
)
_CURRENCIES = (("INR", "INR"), ("USD", "USD"), ("EUR", "EUR"), ("GBP", "GBP"), ("AED", "AED"))
_DEPOSITORIES = (("nsdl", "NSDL"), ("cdsl", "CDSL"))
_CARD_NETWORKS = (
    ("visa", "Visa"), ("mastercard", "Mastercard"), ("rupay", "RuPay"),
    ("amex", "American Express"), ("diners", "Diners Club"),
)
_LOAN_TYPES = (
    (LiabilityType.HOME_LOAN.value, "Home Loan"),
    (LiabilityType.CAR_LOAN.value, "Car Loan"),
    (LiabilityType.PERSONAL_LOAN.value, "Personal Loan"),
    (LiabilityType.EDUCATION_LOAN.value, "Education Loan"),
    (LiabilityType.BNPL.value, "BNPL"),
)


# ---- sections -------------------------------------------------------------
SECTIONS: tuple = (
    Section("account", "Account Details", (
        Field("name", "Name", "text", "TEXT", required=True,
              placeholder="e.g. HDFC Salary Account"),
        Field("account_type", "Type", "combo", "TEXT", _ACCOUNT_TYPES, required=True),
        Field("institution", "Institution", "text", "TEXT", placeholder="e.g. HDFC Bank"),
        Field("account_number", "Account number", "text", "TEXT", placeholder="e.g. XXXX1234"),
        Field("currency", "Currency", "combo", "TEXT", _CURRENCIES),
        Field("opening_balance", "Opening balance", "money", "REAL"),
        Field("current_balance", "Current balance", "money", "REAL"),
    )),
    Section("kyc", "Contact & KYC", (
        Field("phone", "Phone", "text", "TEXT", placeholder="Registered mobile"),
        Field("email", "Email", "text", "TEXT", placeholder="Registered email"),
        Field("ifsc_code", "IFSC code", "text", "TEXT", placeholder="e.g. HDFC0001234"),
        Field("bank_address", "Bank address", "multiline", "TEXT"),
        Field("personal_address", "Personal address", "multiline", "TEXT"),
    )),
    Section("demat", "Demat Account Details", (
        Field("demat_enabled", "Demat enabled", "checkbox", "INTEGER"),
        Field("depository", "Depository", "combo", "TEXT", _DEPOSITORIES),
        Field("dp_id", "DP ID", "text", "TEXT"),
        Field("demat_client_id", "Client ID", "text", "TEXT"),
        Field("demat_bo_id", "BO ID", "text", "TEXT"),
        Field("demat_broker", "Broker / DP name", "text", "TEXT"),
    )),
    Section("investment", "Investment Account Details", (
        Field("investment_enabled", "Investment enabled", "checkbox", "INTEGER"),
        Field("trading_account_number", "Trading account number", "text", "TEXT"),
        Field("investment_broker", "Broker", "text", "TEXT"),
        Field("investment_segments", "Segments", "text", "TEXT",
              placeholder="e.g. Equity, F&O, Currency"),
    )),
    Section("credit_card", "Credit Card Details", (
        Field("cc_network", "Card network", "combo", "TEXT", _CARD_NETWORKS),
        Field("cc_last4", "Card number (last 4)", "text", "TEXT"),
        Field("cc_credit_limit", "Credit limit", "money", "REAL"),
        Field("cc_outstanding", "Outstanding", "money", "REAL"),
        Field("cc_billing_day", "Billing cycle day", "day", "INTEGER"),
        Field("cc_due_day", "Payment due day", "day", "INTEGER"),
    )),
    Section("loan", "Loan Details", (
        Field("loan_type", "Loan type", "combo", "TEXT", _LOAN_TYPES),
        Field("loan_account_number", "Loan account number", "text", "TEXT"),
        Field("loan_principal", "Principal", "money", "REAL"),
        Field("loan_outstanding", "Outstanding", "money", "REAL"),
        Field("loan_interest_rate", "Interest rate", "percent", "REAL"),
        Field("loan_emi", "EMI", "money", "REAL"),
        Field("loan_tenure_months", "Tenure (months)", "int", "INTEGER"),
        Field("loan_start_date", "Start date", "text", "TEXT", placeholder="YYYY-MM-DD"),
    )),
    Section("bond", "Bond Details", (
        Field("bond_issuer", "Issuer", "text", "TEXT"),
        Field("bond_isin", "ISIN", "text", "TEXT"),
        Field("bond_face_value", "Face value", "money", "REAL"),
        Field("bond_coupon_rate", "Coupon rate", "percent", "REAL"),
        Field("bond_units", "Units held", "int", "INTEGER"),
        Field("bond_maturity_date", "Maturity date", "text", "TEXT", placeholder="YYYY-MM-DD"),
    )),
    Section("notes", "Notes", (
        Field("notes", "Notes", "multiline", "TEXT"),
    )),
)

# The section used by the "Add Account" flow (create mode).
ACCOUNT_SECTION = SECTIONS[0]

# Columns that already exist in the base accounts table (not migration adds).
ORIGINAL_COLUMNS = {
    "id", "name", "account_type", "institution", "account_number",
    "opening_balance", "current_balance", "currency", "is_active", "notes",
    "created_at", "updated_at",
}


def iter_fields():
    """Yield every Field across all sections."""
    for section in SECTIONS:
        for f in section.fields:
            yield f


def column_additions() -> dict[str, str]:
    """{column_name: sqltype} for every field that is not an original column.

    Drives db/migrate.py so older databases gain all detail columns.
    """
    out: dict[str, str] = {}
    for f in iter_fields():
        if f.attr not in ORIGINAL_COLUMNS:
            out.setdefault(f.attr, f.sqltype)
    return out


def label_for_value(field: Field, value) -> str:
    """Human label for a combo value; identity for everything else."""
    if field.options:
        for val, lbl in field.options:
            if val == value:
                return lbl
    return "" if value is None else str(value)
