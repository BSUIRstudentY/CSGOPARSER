"""Demand comparison across marketplaces. One row is one skin, not a buy/sell route.

Each quote is the highest buy order (what that market will pay), not the cheapest listing.
Sites with no stored bid are left out. Arbitrage still uses asks.
"""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, money
from app.db.models import Item, Price, Site, User
from app.schemas.common import Page
from app.schemas.market import MarketCardOut, QuoteOut
from app.services.links import listing_url

router = APIRouter(prefix="/market", tags=["market"])


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def demand_usd(price: Price) -> float | None:
    """Highest buy order in USD. Missing or non-positive bids are not a demand quote."""
    raw = (price.details or {}).get("bid_usd")
    if raw is None:
        return None
    try:
        value = Decimal(str(raw))
    except (ArithmeticError, ValueError):
        return None
    if value <= 0:
        return None
    return money(value)


def _card(item: Item, quotes: list[QuoteOut]) -> MarketCardOut | None:
    if len(quotes) < 2:
        return None
    ordered = sorted(quotes, key=lambda quote: quote.price_usd)
    cheapest = ordered[0]
    highest = ordered[-1]
    spread = highest.price_usd - cheapest.price_usd
    spread_pct = (spread / highest.price_usd * 100) if highest.price_usd else 0
    return MarketCardOut(
        item_id=item.id,
        canonical_name=item.canonical_name,
        weapon=item.weapon,
        skin_name=item.skin_name,
        wear=item.wear,
        stattrak=item.stattrak,
        souvenir=item.souvenir,
        cheapest=cheapest,
        highest=highest,
        spread_usd=round(spread, 2),
        spread_pct=round(spread_pct, 2),
        quotes=ordered,
    )


async def _cards(
    db: AsyncSession,
    *,
    q: str | None,
    weapon: str | None,
    wear: str | None,
    item_id: int | None,
) -> list[MarketCardOut]:
    sub = (
        select(Price.item_id, Price.site_id, func.max(Price.id).label("id"))
        .group_by(Price.item_id, Price.site_id)
        .subquery()
    )
    stmt = (
        select(Price, Item, Site)
        .join(sub, Price.id == sub.c.id)
        .join(Item, Item.id == Price.item_id)
        .join(Site, Site.id == Price.site_id)
        .where(Site.enabled.is_(True))
    )
    if item_id is not None:
        stmt = stmt.where(Item.id == item_id)
    if q:
        stmt = stmt.where(Item.canonical_name.ilike(_like(q), escape="\\"))
    if weapon:
        stmt = stmt.where(Item.weapon == weapon)
    if wear:
        stmt = stmt.where(Item.wear == wear)
    rows = (await db.execute(stmt)).all()
    grouped: dict[int, tuple[Item, list[QuoteOut]]] = {}
    for price, item, site in rows:
        bid = demand_usd(price)
        if bid is None:
            continue
        quote = QuoteOut(
            site=site.slug,
            site_name=site.name,
            price_usd=bid,
            listings_count=None,
            url=listing_url(site.slug, item.canonical_name, price.details),
        )
        bucket = grouped.get(item.id)
        if bucket is None:
            grouped[item.id] = (item, [quote])
        else:
            bucket[1].append(quote)
    cards = [card for item, quotes in grouped.values() if (card := _card(item, quotes))]
    cards.sort(key=lambda card: card.spread_usd, reverse=True)
    return cards


@router.get("", response_model=Page[MarketCardOut])
async def list_market(
    q: str | None = None,
    weapon: str | None = None,
    wear: str | None = None,
    min_spread: float | None = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Page[MarketCardOut]:
    cards = await _cards(db, q=q, weapon=weapon, wear=wear, item_id=None)
    if min_spread is not None:
        cards = [card for card in cards if card.spread_usd >= min_spread]
    start = (page - 1) * page_size
    return Page(
        items=cards[start : start + page_size],
        total=len(cards),
        page=page,
        page_size=page_size,
    )


@router.get("/{item_id}", response_model=MarketCardOut)
async def market_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> MarketCardOut:
    cards = await _cards(db, q=None, weapon=None, wear=None, item_id=item_id)
    if not cards:
        raise HTTPException(status_code=404, detail="Not enough marketplace prices for this item")
    return cards[0]
