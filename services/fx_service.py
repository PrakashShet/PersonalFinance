"""Currency conversion into the base currency (INR).

Rates are entered by the user (Settings - there is no network access by design)
and stored in ``data/store/fx_rates.json``. A balance in a currency without a
rate is never silently added as if it were rupees: callers get ``None`` and the
UI says which currency needs a rate.
"""
from __future__ import annotations

from datetime import date
from typing import Callable, Optional

from models.fx_rate import FxRate
from repositories.reference_repos import FxRateRepository

BASE_CURRENCY = "INR"


class FxService:
    def __init__(
        self,
        repo: FxRateRepository,
        on_change: Callable[[str], None] | None = None,
    ) -> None:
        self.repo = repo
        self._on_change = on_change

    def list_rates(self) -> list[FxRate]:
        return self.repo.list_all()

    def rate(self, currency: Optional[str]) -> Optional[float]:
        code = (currency or BASE_CURRENCY).upper()
        if code == BASE_CURRENCY:
            return 1.0
        r = self.repo.get(code)
        return r.rate_to_inr if r and r.rate_to_inr > 0 else None

    def convert(self, amount: float, currency: Optional[str]) -> Optional[float]:
        rate = self.rate(currency)
        return None if rate is None else amount * rate

    def set_rate(self, currency: str, rate_to_inr: float, as_of: Optional[str] = None) -> None:
        code = (currency or "").strip().upper()
        if not code or code == BASE_CURRENCY:
            raise ValueError("Choose a currency other than INR")
        if rate_to_inr <= 0:
            raise ValueError("The rate must be greater than zero")
        self.repo.upsert(code, float(rate_to_inr), as_of or date.today().isoformat())
        self._changed()

    def delete_rate(self, currency: str) -> None:
        self.repo.delete(currency.upper())
        self._changed()

    def _changed(self) -> None:
        if self._on_change is not None:
            self._on_change("fx_rates")
            self._on_change("accounts")
