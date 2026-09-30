"""Item catalog and price history."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_cache, get_current_user, get_db, money
from app.api.routes.market import demand_usd
from app.db.models import Item, Price, User
from app.schemas.common import Page
from app.schemas.market import ItemOut, OpportunityOut, PricePointOut
from app.services.cache import PriceCache
from app.services.opportunities import latest_prices_for_item

router = APIRouter(prefix="/items", tags=["items"])


def _bid_usd(row: Price) -> float | None:
    return demand_usd(row)


def _cached_bid(raw: object) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


def _item_out(item: Item) -> ItemOut:
    return ItemOut(
        id=item.id,
        game=item.game,
        weapon=item.weapon,
        skin_name=item.skin_name,
        wear=item.wear,
        stattrak=item.stattrak,
        souvenir=item.souvenir,
        canonical_name=item.canonical_name,
    )


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("/facets")
async def facets(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict[str, list[str]]:
    weapons = (
        (await db.execute(select(Item.weapon).distinct().order_by(Item.weapon))).scalars().all()
    )
    return {"weapons": list(weapons), "wears": ["FN", "MW", "FT", "WW", "BS"]}


@router.get("", response_model=Page[ItemOut])
async def list_items(
    q: str | None = None,
    weapon: str | None = None,
    wear: str | None = None,
    stattrak: bool | None = None,
    souvenir: bool | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Page[ItemOut]:
    stmt = select(Item)
    if q:
        stmt = stmt.where(Item.canonical_name.ilike(_like(q), escape="\\"))
    if weapon:
        stmt = stmt.where(Item.weapon == weapon)
    if wear:
        stmt = stmt.where(Item.wear == wear)
    if stattrak is not None:
        stmt = stmt.where(Item.stattrak.is_(stattrak))
    if souvenir is not None:
        stmt = stmt.where(Item.souvenir.is_(souvenir))
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (
        (
            await db.execute(
                stmt.order_by(Item.canonical_name).offset((page - 1) * page_size).limit(page_size)
            )
        )
        .scalars()
        .all()
    )
    return Page(
        items=[_item_out(row) for row in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


@router.get("/{item_id}", response_model=ItemOut)
async def get_item(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> ItemOut:
    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return _item_out(item)


@router.get("/{item_id}/prices", response_model=list[PricePointOut])
async def price_history(
    item_id: int,
    hours: int = Query(default=24 * 14, ge=1, le=24 * 90),
    site: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[PricePointOut]:
    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    since = datetime.now(UTC) - timedelta(hours=hours)
    stmt = (
        select(Price)
        .options(selectinload(Price.site))
        .where(Price.item_id == item_id, Price.captured_at >= since)
        .order_by(Price.captured_at)
    )
    rows = (await db.execute(stmt)).scalars().all()
    points: list[PricePointOut] = []
    for row in rows:
        if site and row.site.slug != site:
            continue
        points.append(
            PricePointOut(
                site=row.site.slug,
                price=money(row.price),
                price_usd=money(row.price_usd),
                currency=row.currency,
                listings_count=row.listings_count,
                volume_24h=row.volume_24h,
                captured_at=row.captured_at,
                bid_usd=_bid_usd(row),
            )
        )
    return points


@router.get("/{item_id}/latest", response_model=list[PricePointOut])
async def latest_prices(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    cache: PriceCache = Depends(get_cache),
    _: User = Depends(get_current_user),
) -> list[PricePointOut]:
    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    cached = await cache.get_item(item_id)
    if cached:
        return [
            PricePointOut(
                site=str(row["site"]),
                price=float(row["price"]),
                price_usd=float(row["price_usd"]),
                currency=str(row["currency"]),
                listings_count=row.get("listings_count"),
                volume_24h=row.get("volume_24h"),
                captured_at=row["captured_at"],
                bid_usd=_cached_bid(row.get("bid_usd")),
            )
            for row in cached
        ]
    rows = await latest_prices_for_item(db, item_id)
    points = [
        PricePointOut(
            site=row.site.slug,
            price=money(row.price),
            price_usd=money(row.price_usd),
            currency=row.currency,
            listings_count=row.listings_count,
            volume_24h=row.volume_24h,
            captured_at=row.captured_at,
            bid_usd=_bid_usd(row),
        )
        for row in rows
    ]
    for row in rows:
        await cache.put_quote(
            item_id,
            row.site.slug,
            {
                "site": row.site.slug,
                "price": money(row.price),
                "price_usd": money(row.price_usd),
                "currency": row.currency,
                "listings_count": row.listings_count,
                "volume_24h": row.volume_24h,
                "bid_usd": _bid_usd(row),
                "captured_at": row.captured_at.isoformat(),
            },
        )
    return points


@router.get("/{item_id}/opportunities", response_model=list[OpportunityOut])
async def item_opportunities(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[OpportunityOut]:
    from app.api.routes.arbitrage import list_opportunities_for_item

    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return await list_opportunities_for_item(db, item_id)
