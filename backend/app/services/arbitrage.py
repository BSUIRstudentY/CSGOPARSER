"""Net profit for a buy-on-A / sell-on-B route.

Sell price is the current lowest ask on the destination, not a filled bid.
The figure is the profit if you buy the cheapest listing on A and relist on B
at B's current lowest ask. It is an estimate of the spread, not a guaranteed fill.

Steam purchases cannot be traded for trade_lock_days (default 7). Those routes
are marked instant_trade=False so the dashboard can hide them.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


def as_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass(frozen=True)
class FeeSchedule:
    buy_fee_pct: Decimal = Decimal("0")
    sell_fee_pct: Decimal = Decimal("0")
    deposit_fee_pct: Decimal = Decimal("0")
    deposit_fee_flat: Decimal = Decimal("0")
    withdraw_fee_pct: Decimal = Decimal("0")
    withdraw_fee_flat: Decimal = Decimal("0")

    @classmethod
    def from_site(cls, site: Any) -> "FeeSchedule":
        return cls(
            buy_fee_pct=as_decimal(site.buy_fee_pct),
            sell_fee_pct=as_decimal(site.sell_fee_pct),
            deposit_fee_pct=as_decimal(site.deposit_fee_pct),
            deposit_fee_flat=as_decimal(site.deposit_fee_flat),
            withdraw_fee_pct=as_decimal(site.withdraw_fee_pct),
            withdraw_fee_flat=as_decimal(site.withdraw_fee_flat),
        )


@dataclass(frozen=True)
class ProfitBreakdown:
    cost_usd: Decimal
    proceeds_usd: Decimal
    profit_usd: Decimal
    profit_pct: Decimal


def net_profit(
    buy_price_usd: Decimal,
    sell_price_usd: Decimal,
    buy_fees: FeeSchedule,
    sell_fees: FeeSchedule,
) -> ProfitBreakdown:
    """Apply the buy site's deposit/buy fees and the sell site's sell/withdraw fees.

    profit = sell*(1-sell_fee) - sell*withdraw_fee - withdraw_flat
             - buy*(1+buy_fee) - buy*deposit_fee - deposit_flat
    """
    buy = as_decimal(buy_price_usd)
    sell = as_decimal(sell_price_usd)
    cost = (
        buy * (Decimal("1") + buy_fees.buy_fee_pct)
        + buy * buy_fees.deposit_fee_pct
        + buy_fees.deposit_fee_flat
    )
    proceeds = (
        sell * (Decimal("1") - sell_fees.sell_fee_pct)
        - sell * sell_fees.withdraw_fee_pct
        - sell_fees.withdraw_fee_flat
    )
    profit = proceeds - cost
    if cost > 0:
        profit_pct = (profit / cost) * Decimal("100")
    else:
        profit_pct = Decimal("0")
    return ProfitBreakdown(
        cost_usd=_q(cost),
        proceeds_usd=_q(proceeds),
        profit_usd=_q(profit),
        profit_pct=_q(profit_pct),
    )


def liquidity_score(buy_listings: int | None, sell_listings: int | None) -> int:
    """Both sides must have listings. Unknown counts count as zero."""
    return min(buy_listings or 0, sell_listings or 0)


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))
