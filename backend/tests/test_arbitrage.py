from decimal import Decimal

from app.services.arbitrage import FeeSchedule, liquidity_score, net_profit


def test_profit_matches_fee_formula() -> None:
    buy = FeeSchedule(
        buy_fee_pct=Decimal("0.02"),
        deposit_fee_pct=Decimal("0.01"),
        deposit_fee_flat=Decimal("0.30"),
    )
    sell = FeeSchedule(
        sell_fee_pct=Decimal("0.12"),
        withdraw_fee_pct=Decimal("0.01"),
        withdraw_fee_flat=Decimal("0.50"),
    )
    result = net_profit(Decimal("100"), Decimal("150"), buy, sell)
    assert result.cost_usd == Decimal("103.3000")
    assert result.proceeds_usd == Decimal("130.0000")
    assert result.profit_usd == Decimal("26.7000")
    assert result.profit_pct == Decimal("25.8470")


def test_zero_cost_does_not_divide() -> None:
    result = net_profit(Decimal("0"), Decimal("10"), FeeSchedule(), FeeSchedule())
    assert result.profit_pct == Decimal("0.0000")
    assert result.profit_usd == Decimal("10.0000")


def test_sell_fee_can_wipe_out_a_higher_ask() -> None:
    sell = FeeSchedule(sell_fee_pct=Decimal("0.15"))
    result = net_profit(Decimal("100"), Decimal("110"), FeeSchedule(), sell)
    assert result.proceeds_usd == Decimal("93.5000")
    assert result.profit_usd < 0


def test_liquidity_uses_the_thinner_side() -> None:
    assert liquidity_score(4, 10) == 4
    assert liquidity_score(None, 8) == 0
    assert liquidity_score(3, None) == 0
