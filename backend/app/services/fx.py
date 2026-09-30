"""Convert marketplace currencies into USD using rates stored in the database."""

from decimal import Decimal

from app.services.arbitrage import as_decimal


class UnknownCurrencyError(Exception):
    def __init__(self, currency: str) -> None:
        super().__init__(f"No FX rate configured for {currency}")
        self.currency = currency


def to_usd(amount: Decimal, currency: str, rates: dict[str, Decimal]) -> Decimal:
    code = currency.upper()
    if code not in rates:
        raise UnknownCurrencyError(code)
    usd = as_decimal(amount) * rates[code]
    return usd.quantize(Decimal("0.0001"))
