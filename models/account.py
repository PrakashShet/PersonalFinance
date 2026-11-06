from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from models.base import BaseModel


@dataclass
class Account(BaseModel):
    id: Optional[int] = None
    name: str = ""
    account_type: str = "savings"
    institution: Optional[str] = None
    account_number: Optional[str] = None
    opening_balance: float = 0.0
    current_balance: float = 0.0
    currency: str = "INR"
    is_active: int = 1
    notes: Optional[str] = None

    # Contact & KYC
    phone: Optional[str] = None
    email: Optional[str] = None
    ifsc_code: Optional[str] = None
    bank_address: Optional[str] = None
    personal_address: Optional[str] = None  # address on record with the bank

    # Demat account details
    demat_enabled: int = 0
    depository: Optional[str] = None         # NSDL / CDSL
    dp_id: Optional[str] = None
    demat_client_id: Optional[str] = None
    demat_bo_id: Optional[str] = None
    demat_broker: Optional[str] = None

    # Investment account details
    investment_enabled: int = 0
    trading_account_number: Optional[str] = None
    investment_broker: Optional[str] = None
    investment_segments: Optional[str] = None

    # Credit card details
    cc_network: Optional[str] = None
    cc_last4: Optional[str] = None
    cc_credit_limit: float = 0.0
    cc_outstanding: float = 0.0
    cc_billing_day: int = 0
    cc_due_day: int = 0

    # Loan details
    loan_type: Optional[str] = None
    loan_account_number: Optional[str] = None
    loan_principal: float = 0.0
    loan_outstanding: float = 0.0
    loan_interest_rate: float = 0.0
    loan_emi: float = 0.0
    loan_tenure_months: int = 0
    loan_start_date: Optional[str] = None

    # Bond details
    bond_issuer: Optional[str] = None
    bond_isin: Optional[str] = None
    bond_face_value: float = 0.0
    bond_coupon_rate: float = 0.0
    bond_units: int = 0
    bond_maturity_date: Optional[str] = None

    created_at: Optional[str] = None
    updated_at: Optional[str] = None
