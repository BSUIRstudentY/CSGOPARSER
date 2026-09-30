"""Rebuild stored arbitrage routes from the latest ask on each marketplace."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ArbitrageOpportunity, Price, Site
from app.services.arbitrage import FeeSchedule, liquidity_score, net_profit


async def latest_prices_for_item(session: AsyncSession, item_id: int) -> list[Price]:
    sub = (
        select(Price.site_id, func.max(Price.id).label("id"))
        .where(Price.item_id == item_id)
        .group_by(Price.site_id)
        .subquery()
    )
    result = await session.execute(
        select(Price).options(selectinload(Price.site)).join(sub, Price.id == sub.c.id)
    )
    return list(result.scalars().all())


async def recompute_opportunities(session: AsyncSession, min_profit_pct: Decimal) -> int:
    site_result = await session.execute(select(Site).where(Site.enabled.is_(True)))
    sites = {site.id: site for site in site_result.scalars().all()}
    if len(sites) < 2:
        await session.execute(delete(ArbitrageOpportunity))
        await session.commit()
        return 0

    sub = (
        select(Price.item_id, Price.site_id, func.max(Price.id).label("id"))
        .where(Price.site_id.in_(sites.keys()))
        .group_by(Price.item_id, Price.site_id)
        .subquery()
    )
    price_result = await session.execute(select(Price).join(sub, Price.id == sub.c.id))
    by_item: dict[int, dict[int, Price]] = {}
    for price in price_result.scalars().all():
        by_item.setdefault(price.item_id, {})[price.site_id] = price

    await session.execute(delete(ArbitrageOpportunity))
    now = datetime.now(UTC)
    written = 0
    pending: list[ArbitrageOpportunity] = []
    floor = min_profit_pct

    for item_id, quotes in by_item.items():
        available = [site_id for site_id in quotes if site_id in sites]
        for buy_id in available:
            for sell_id in available:
                if buy_id == sell_id:
                    continue
                buy_site = sites[buy_id]
                sell_site = sites[sell_id]
                buy_price = quotes[buy_id].price_usd
                sell_price = quotes[sell_id].price_usd
                if buy_price <= 0 or sell_price <= 0:
                    continue
                breakdown = net_profit(
                    buy_price,
                    sell_price,
                    FeeSchedule.from_site(buy_site),
                    FeeSchedule.from_site(sell_site),
                )
                if breakdown.profit_pct < floor:
                    continue
                lock_days = buy_site.trade_lock_days
                pending.append(
                    ArbitrageOpportunity(
                        item_id=item_id,
                        buy_site_id=buy_id,
                        sell_site_id=sell_id,
                        buy_price_usd=buy_price,
                        sell_price_usd=sell_price,
                        cost_usd=breakdown.cost_usd,
                        proceeds_usd=breakdown.proceeds_usd,
                        profit_usd=breakdown.profit_usd,
                        profit_pct=breakdown.profit_pct,
                        liquidity=liquidity_score(
                            quotes[buy_id].listings_count,
                            quotes[sell_id].listings_count,
                        ),
                        instant_trade=lock_days == 0,
                        trade_lock_days=lock_days,
                        cash_out=sell_site.cash_out,
                        computed_at=now,
                        is_active=True,
                    )
                )
                written += 1
                if len(pending) >= 500:
                    session.add_all(pending)
                    pending = []
    if pending:
        session.add_all(pending)
    await session.commit()
    return written
