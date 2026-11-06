"""Domain enums and shared constants."""
from __future__ import annotations

from enum import Enum


class AccountType(str, Enum):
    SAVINGS = "savings"
    CURRENT = "current"
    SALARY = "salary"
    CASH = "cash"
    WALLET = "wallet"          # PhonePe / GPay / Paytm
    CREDIT_CARD = "credit_card"  # liability


class TransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    INVESTMENT_BUY = "investment_buy"
    INVESTMENT_SELL = "investment_sell"


class IncomeSource(str, Enum):
    SALARY = "salary"
    WEB_APP = "web_app"
    TRADING = "trading"
    FREELANCE = "freelance"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    RENTAL = "rental"
    OTHER = "other"


class HoldingType(str, Enum):
    TERM_INSURANCE = "term_insurance"
    SIP = "sip"
    MUTUAL_FUND = "mutual_fund"
    ETF = "etf"
    FD = "fd"
    GOLD_JEWELRY = "gold_jewelry"
    GOLD_COIN = "gold_coin"
    STOCK = "stock"
    PPF = "ppf"
    EPF = "epf"
    NPS = "nps"
    BOND = "bond"
    CRYPTO = "crypto"
    REAL_ESTATE = "real_estate"


class StockCap(str, Enum):
    SME = "sme"
    SMALL = "small_cap"
    MID = "mid_cap"
    LARGE = "large_cap"


class LiabilityType(str, Enum):
    HOME_LOAN = "home_loan"
    CAR_LOAN = "car_loan"
    PERSONAL_LOAN = "personal_loan"
    CREDIT_CARD = "credit_card"
    EDUCATION_LOAN = "education_loan"
    BNPL = "bnpl"


class GoalStatus(str, Enum):
    ACTIVE = "active"
    ACHIEVED = "achieved"
    PAUSED = "paused"
    ABANDONED = "abandoned"


# Asset allocation buckets for the dashboard
ASSET_BUCKETS = {
    "equity": [HoldingType.SIP, HoldingType.MUTUAL_FUND, HoldingType.ETF, HoldingType.STOCK],
    "debt":   [HoldingType.FD, HoldingType.PPF, HoldingType.EPF, HoldingType.BOND],
    "gold":   [HoldingType.GOLD_COIN, HoldingType.GOLD_JEWELRY],
    "alt":    [HoldingType.CRYPTO, HoldingType.REAL_ESTATE, HoldingType.NPS],
    "insurance": [HoldingType.TERM_INSURANCE],
}
