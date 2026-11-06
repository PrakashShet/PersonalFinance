"""Build a fictional demo store: for the user guide's screenshots, for trying
the app, and for testing - never anyone's real data.

Everything goes through the app's own services, so the demo obeys the same
rules as real data (balances equal their transactions, recurring tags, budget
limits). Dates are relative to today, so the dashboard always looks current;
nothing is dated in the future.

    python tools/make_demo_store.py <new-folder>
    set PFM_HOME=<new-folder> && run.bat          :: open the app on the demo

The folder must not exist yet. The demo lands in <new-folder>/data/store.
"""
from __future__ import annotations

import math
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _month(today: date, back: int) -> date:
    total = today.year * 12 + today.month - 1 - back
    return date(total // 12, total % 12 + 1, 1)


def _day(month_start: date, day: int) -> date:
    nxt = _month(month_start, -1)
    last = (nxt - timedelta(days=1)).day
    return month_start.replace(day=min(day, last))


def build(ctx, today: date | None = None, months: int = 6) -> None:
    """Fill an empty, open store with a fictional household's last ``months``."""
    from models.account import Account
    from models.goal import Goal
    from models.holding import Holding
    from models.income import IncomeSource
    from models.liability import Liability
    from models.transaction import Transaction
    from services import ledger

    today = today or date.today()
    start = _month(today, months)
    cats = {name: cid for cid, name in ctx.expense_categories()}
    txns = ctx.transaction_service

    def post(when: date, kind: str, amount: float, account: int, *, category=None, note=None,
             to=None, holding=None, tags=None) -> None:
        if when > today:
            return                                   # the demo never looks ahead
        txns.create_transaction(Transaction(
            txn_date=when.isoformat(), txn_type=kind, amount=round(amount, 2), account_id=account,
            counter_account_id=to, category_id=cats.get(category) if category else None,
            holding_id=holding, description=note, tags=tags))

    # --- accounts (opening balances dated at the start of the demo) ----------
    db = ctx.net_worth_service.db

    def account(name, kind, institution, number, opening) -> int:
        aid = ctx.account_service.create_account(Account(
            name=name, account_type=kind, institution=institution, account_number=number))
        txns.create_adjustment(aid, opening, f"Opening balance: {name}",
                               tags=ledger.OPENING_TAG, txn_date=start.isoformat())
        db.execute("UPDATE accounts SET opening_balance = ? WHERE id = ?", (opening, aid))
        db.commit()
        return aid

    salary_acct = account("Salary Account", "salary", "Axis Bank", "XXXX4821", 1_20_000)
    savings = account("Savings Account", "savings", "State Bank of India", "XXXX7730", 3_50_000)
    cash = account("Cash", "cash", None, None, 8_000)
    wallet = account("UPI Wallet", "wallet", "Paytm", None, 2_000)

    # --- income ---------------------------------------------------------------
    income = ctx.income_source_service
    salary_id = income.create(IncomeSource(
        name="Salary", source_type="salary", employer="Northwind Labs", frequency="monthly",
        basic=70_000, hra=28_000, special_allow=42_000, pf_employee=8_400, pf_employer=8_400,
        professional_tax=200, tds=14_000, deposit_account_id=salary_acct))
    rent_id = income.create(IncomeSource(
        name="Flat rent", source_type="rental", frequency="monthly", expected_amount=18_000,
        deposit_account_id=savings, notes="1BHK in Whitefield"))
    salary_src, rent_src = income.get(salary_id), income.get(rent_id)
    take_home = income.net_monthly(salary_src)

    # --- investments, protection, loans ----------------------------------------
    inv = ctx.investment_service
    sip_a_day, sip_b_day = min(today.day + 4, 28), min(today.day + 9, 28)
    nifty = inv.add_holding(Holding(
        name="Nifty 50 Index Fund", holding_type="sip", institution="UTI Mutual Fund",
        purchase_date=(today - timedelta(days=940)).isoformat(), invested_amount=3_10_000,
        current_value=3_72_500, sip_amount=10_000, sip_day_of_month=sip_a_day,
        linked_account_id=salary_acct))
    flexi = inv.add_holding(Holding(
        name="Flexi Cap Fund - Direct", holding_type="sip", institution="PPFAS Mutual Fund",
        purchase_date=(today - timedelta(days=660)).isoformat(), invested_amount=1_10_000,
        current_value=1_26_800, sip_amount=5_000, sip_day_of_month=sip_b_day,
        linked_account_id=salary_acct))
    ppf = inv.add_holding(Holding(
        name="Public Provident Fund", holding_type="ppf", institution="State Bank of India",
        purchase_date=(today - timedelta(days=700)).isoformat(), invested_amount=4_50_000,
        current_value=5_12_000))
    inv.add_holding(Holding(
        name="Fixed deposit - 2 years", holding_type="fd", institution="State Bank of India",
        purchase_date=(today - timedelta(days=710)).isoformat(), invested_amount=2_00_000,
        current_value=2_29_500, interest_rate=7.1,
        maturity_date=(today + timedelta(days=20)).isoformat(), linked_account_id=savings))
    inv.add_holding(Holding(
        name="Gold coins (20 g)", holding_type="gold_coin", institution="Kalyan Jewellers",
        purchase_date="2022-10-24", invested_amount=1_02_000, current_value=1_46_000,
        weight_grams=20, purity="24K"))
    inv.add_holding(Holding(
        name="Infosys", holding_type="stock", institution="Upstox", symbol="INFY",
        exchange="NSE", market_cap="large_cap", sector="IT", quantity=40, avg_price=1_450,
        current_price=1_580, invested_amount=58_000, current_value=63_200,
        purchase_date=(today - timedelta(days=400)).isoformat()))
    inv.add_holding(Holding(
        name="Term plan - 1 Cr cover", holding_type="term_insurance", institution="LIC",
        sum_assured=1_00_00_000, premium_amount=14_500, policy_term_years=30,
        premium_due_date=(today + timedelta(days=9)).isoformat(), linked_account_id=salary_acct))

    car = ctx.liability_service.create(Liability(
        name="Car loan", liability_type="car_loan", lender="Axis Bank", principal=6_50_000,
        outstanding=4_05_600, interest_rate=9.2, emi_amount=14_800, tenure_months=48,
        remaining_months=30, start_date=_month(today, 18).isoformat(),
        next_due_date=(today + timedelta(days=4)).isoformat(), account_id=salary_acct))
    ctx.liability_service.create(Liability(
        name="Credit card bill", liability_type="credit_card", lender="Axis Bank",
        principal=12_300, outstanding=12_300,
        next_due_date=(today + timedelta(days=12)).isoformat()))
    emi_day = (today + timedelta(days=4)).day

    # --- six months of everyday life -------------------------------------------
    wobble = [1.00, 1.08, 0.94, 1.12, 0.97, 1.05, 0.99]
    for back in range(months, 0, -1):
        m = _month(today, back)
        ym = m.strftime("%Y-%m")
        f = wobble[back % len(wobble)]
        income.record_month(salary_src, period_month=ym, actual_amount=take_home,
                            received_date=_day(m, 1).isoformat(), account_id=salary_acct)
        income.record_month(rent_src, period_month=ym, actual_amount=18_000,
                            received_date=_day(m, 5).isoformat(), account_id=savings)
        post(_day(m, 2), "expense", 28_000, salary_acct, category="Rent", note="House rent")
        post(_day(m, 3), "transfer", 20_000, salary_acct, to=savings, note="Monthly savings")
        post(_day(m, 6), "transfer", 3_000, salary_acct, to=cash, note="ATM withdrawal")
        post(_day(m, 8), "transfer", 3_000, salary_acct, to=wallet, note="Wallet top-up")
        post(_day(m, emi_day), "expense", 14_800, salary_acct, category="EMI",
             note="EMI - Car loan", tags=f"emi:{car}:{ym}")
        post(_day(m, sip_a_day), "investment_buy", 10_000, salary_acct, holding=nifty,
             note="SIP - Nifty 50 Index Fund", tags=f"sip:{nifty}:{ym}")
        post(_day(m, sip_b_day), "investment_buy", 5_000, salary_acct, holding=flexi,
             note="SIP - Flexi Cap Fund - Direct", tags=f"sip:{flexi}:{ym}")
        for day, amount, acct, note in [(4, 3_150, salary_acct, "DMart"),
                                        (11, 2_840, cash, "Vegetables and fruit"),
                                        (18, 3_420, salary_acct, "BigBasket"),
                                        (25, 1_980, salary_acct, "Monthly staples")]:
            post(_day(m, day), "expense", round(amount * f, -1), acct, category="Groceries", note=note)
        for day, amount, acct, note in [(6, 650, wallet, "Lunch"), (9, 1_240, salary_acct, "Swiggy"),
                                        (14, 480, wallet, "Coffee"), (20, 2_280, salary_acct, "Dinner out"),
                                        (27, 890, salary_acct, "Zomato")]:
            post(_day(m, day), "expense", round(amount * f, -1), acct, category="Food & Dining", note=note)
        post(_day(m, 7), "expense", round(2_100 * f, -1), salary_acct, category="Fuel", note="Petrol")
        post(_day(m, 22), "expense", round(1_900 * f, -1), salary_acct, category="Fuel", note="Petrol")
        post(_day(m, 10), "expense", round(1_650 * f, -1), salary_acct, category="Utilities", note="Electricity")
        post(_day(m, 5), "expense", 999, salary_acct, category="Internet & Mobile", note="Broadband")
        post(_day(m, 12), "expense", 399, salary_acct, category="Internet & Mobile", note="Mobile recharge")
        post(_day(m, 15), "expense", 499, salary_acct, category="Subscriptions", note="Streaming")
        post(_day(m, 17), "expense", round(3_200 * f * (2 if back == 3 else 1), -1), salary_acct,
             category="Shopping", note="Clothes" if back % 2 else "Home things")
        post(_day(m, 21), "expense", 850, salary_acct, category="Entertainment", note="Movies")
        post(_day(m, 13), "expense", 380, wallet, category="Transport", note="Auto")
        post(_day(m, 26), "expense", 520, wallet, category="Transport", note="Cab")
        if back == 4:
            post(_day(m, 16), "expense", 1_200, cash, category="Healthcare", note="Doctor visit")
        if back == 3:
            post(_day(m, 12), "expense", 24_000, salary_acct, category="Travel", note="Goa trip")
        if back == 1:
            post(_day(m, 19), "expense", 8_500, salary_acct, category="Travel", note="Weekend in Coorg")

    # --- this month so far: one category near its limit, one over ------------------
    m = _month(today, 0)
    income.record_month(salary_src, period_month=m.strftime("%Y-%m"), actual_amount=take_home,
                        received_date=_day(m, 1).isoformat(), account_id=salary_acct)
    for day, kind, amount, acct, category, note in [
        (1, "expense", 1_200, salary_acct, "Food & Dining", "Swiggy"),
        (2, "expense", 28_000, salary_acct, "Rent", "House rent"),
        (2, "expense", 3_200, salary_acct, "Groceries", "DMart"),
        (2, "expense", 900, salary_acct, "Entertainment", "Movies"),
        (3, "expense", 2_300, salary_acct, "Food & Dining", "Dinner out"),
        (3, "expense", 2_000, salary_acct, "Fuel", "Petrol"),
        (4, "expense", 5_800, salary_acct, "Shopping", "Festive shopping"),
        (5, "expense", 2_850, cash, "Groceries", "Vegetables and fruit"),
        (5, "expense", 1_450, wallet, "Food & Dining", "Lunch with team"),
        (5, "expense", 999, salary_acct, "Internet & Mobile", "Broadband"),
        (6, "expense", 450, wallet, "Transport", "Cab"),
    ]:
        post(_day(m, day), kind, amount, acct, category=category, note=note)
    post(_day(m, 3), "transfer", 20_000, salary_acct, to=savings, note="Monthly savings")

    # --- goals and budgets ----------------------------------------------------
    goals = ctx.goal_service
    goals.create(Goal(name="Emergency fund", target_amount=6_00_000, current_amount=4_20_000,
                      target_date=date(today.year + 1, 3, 31).isoformat(), priority=1,
                      expected_return=0.07))
    goals.create(Goal(name="Home down payment", target_amount=25_00_000,
                      target_date=date(today.year + 4, 12, 31).isoformat(), priority=2,
                      expected_return=0.11), [nifty, flexi])
    goals.create(Goal(name="Retirement", target_amount=5_00_00_000,
                      target_date=date(today.year + 29, 12, 31).isoformat(), priority=3,
                      expected_return=0.10), [ppf])

    budgets = ctx.budget_service
    budgets.set_limit(cats["Groceries"], "monthly", 12_000)
    budgets.set_limit(cats["Food & Dining"], "monthly", 6_000, "Includes Swiggy and Zomato")
    budgets.set_limit(cats["Shopping"], "monthly", 5_000)
    budgets.set_limit(cats["Fuel"], "monthly", 4_500)
    budgets.set_limit(cats["Entertainment"], "monthly", 2_000)
    budgets.set_limit(cats["Travel"], "yearly", 1_50_000, "Two trips a year")

    # --- a net-worth history: weekly snapshots trending to today's figure ----------
    bs = ctx.net_worth_service.compute()
    snaps = ctx.net_worth_service.snapshots
    days = (today - start).days
    for d in range(0, days - 6, 7):
        t = d / days
        liab = bs.total_liabilities + (1 - t) * months * 9_200
        worth = bs.net_worth - (1 - t) * 3_10_000 + 18_000 * math.sin(d / 9.0)
        snaps.upsert((start + timedelta(days=d)).isoformat(), worth + liab, liab, worth, None)
    ctx.net_worth_service.take_snapshot()


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    home = Path(sys.argv[1]).resolve()
    if home.exists():
        print(f"{home} already exists - give a new folder so nothing is overwritten.")
        return 2
    os.environ["PFM_HOME"] = str(home)
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)

    from config.settings import settings
    from db.connection import db
    from services.app_context import AppContext
    from services.storage import Storage

    assert Path(settings.STORE_DIR).resolve().is_relative_to(home), "refusing to touch real data"
    db.connect(":memory:")
    storage = Storage(db, settings.STORE_DIR, settings.BACKUP_DIR, settings.SEED_DIR,
                      settings.REFERENCE_DIR, settings.SCHEMA_PATH, settings.APP_VERSION)
    storage.open()
    build(AppContext.create(db, storage=storage))
    storage.close()
    db.close()
    print(f"Demo store written to {settings.STORE_DIR}")
    print(f"Open it with:  set PFM_HOME={home}  and then  run.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
