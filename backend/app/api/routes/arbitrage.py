"""Arbitrage search."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import Select

from app.api.deps import get_current_user, get_db, money
from app.db.models import ArbitrageOpportunity, Item, Site, User
from app.schemas.common import Page
from app.schemas.market import OpportunityOut

router = APIRouter(prefix="/arbitrage", tags=["arbitrage"])


def opportunity_out(row: ArbitrageOpportunity) -> OpportunityOut:
    return OpportunityOut(
        id=row.id,
        item_id=row.item_id,
        canonical_name=row.item.canonical_name,
        weapon=row.item.weapon,
        skin_name=row.item.skin_name,
        wear=row.item.wear,
        stattrak=row.item.stattrak,
        souvenir=row.item.souvenir,
        buy_site=row.buy_site.slug,
        sell_site=row.sell_site.slug,
        buy_price_usd=money(row.buy_price_usd),
        sell_price_usd=money(row.sell_price_usd),
        cost_usd=money(row.cost_usd),
        proceeds_usd=money(row.proceeds_usd),
        profit_usd=money(row.profit_usd),
        profit_pct=money(row.profit_pct),
        liquidity=row.liquidity,
        instant_trade=row.instant_trade,
        trade_lock_days=row.trade_lock_days,
        cash_out=row.cash_out,
        computed_at=row.computed_at,
    )


def _like(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def apply_filters(
    stmt: Select[ArbitrageOpportunity],
    *,
    q: str | None,
    weapon: str | None,
    wear: str | None,
    stattrak: bool | None,
    souvenir: bool | None,
    min_profit: float | None,
    min_profit_pct: float | None,
    min_liquidity: int | None,
    buy_ids: list[int],
    sell_ids: list[int],
    exclude_ids: list[int],
    instant_only: bool,
    cash_out_only: bool,
) -> Select[ArbitrageOpportunity]:
    query = stmt
    if q:
        query = query.where(Item.canonical_name.ilike(_like(q), escape="\\"))
    if weapon:
        query = query.where(Item.weapon == weapon)
    if wear:
        query = query.where(Item.wear == wear)
    if stattrak is not None:
        query = query.where(Item.stattrak.is_(stattrak))
    if souvenir is not None:
        query = query.where(Item.souvenir.is_(souvenir))
    if min_profit is not None:
        query = query.where(ArbitrageOpportunity.profit_usd >= min_profit)
    if min_profit_pct is not None:
        query = query.where(ArbitrageOpportunity.profit_pct >= min_profit_pct)
    if min_liquidity is not None:
        query = query.where(ArbitrageOpportunity.liquidity >= min_liquidity)
    if buy_ids:
        query = query.where(ArbitrageOpportunity.buy_site_id.in_(buy_ids))
    if sell_ids:
        query = query.where(ArbitrageOpportunity.sell_site_id.in_(sell_ids))
    if exclude_ids:
        query = query.where(ArbitrageOpportunity.buy_site_id.notin_(exclude_ids))
        query = query.where(ArbitrageOpportunity.sell_site_id.notin_(exclude_ids))
    if instant_only:
        query = query.where(ArbitrageOpportunity.instant_trade.is_(True))
    if cash_out_only:
        query = query.where(ArbitrageOpportunity.cash_out.is_(True))
    return query


SORTS = {
    "profit": ArbitrageOpportunity.profit_usd,
    "profit_pct": ArbitrageOpportunity.profit_pct,
    "liquidity": ArbitrageOpportunity.liquidity,
    "computed_at": ArbitrageOpportunity.computed_at,
    "name": Item.canonical_name,
}


async def _site_ids(db: AsyncSession, slugs: list[str]) -> list[int]:
    if not slugs:
        return []
    result = await db.execute(select(Site.id).where(Site.slug.in_(slugs)))
    return list(result.scalars().all())


def _base_stmt() -> Select[ArbitrageOpportunity]:
    return (
        select(ArbitrageOpportunity)
        .join(Item, Item.id == ArbitrageOpportunity.item_id)
        .where(ArbitrageOpportunity.is_active.is_(True))
    )


@router.get("", response_model=Page[OpportunityOut])
async def list_arbitrage(
    q: str | None = None,
    weapon: str | None = None,
    wear: str | None = None,
    stattrak: bool | None = None,
    souvenir: bool | None = None,
    min_profit: float | None = None,
    min_profit_pct: float | None = None,
    min_liquidity: int | None = Query(default=None, ge=0),
    buy_site: list[str] = Query(default=[]),
    sell_site: list[str] = Query(default=[]),
    exclude_site: list[str] = Query(default=[]),
    instant_only: bool = False,
    cash_out_only: bool = False,
    sort: str = Query(default="profit_pct"),
    direction: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> Page[OpportunityOut]:
    stmt = apply_filters(
        _base_stmt(),
        q=q,
        weapon=weapon,
        wear=wear,
        stattrak=stattrak,
        souvenir=souvenir,
        min_profit=min_profit,
        min_profit_pct=min_profit_pct,
        min_liquidity=min_liquidity,
        buy_ids=await _site_ids(db, buy_site),
        sell_ids=await _site_ids(db, sell_site),
        exclude_ids=await _site_ids(db, exclude_site),
        instant_only=instant_only,
        cash_out_only=cash_out_only,
    )
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    column = SORTS.get(sort, ArbitrageOpportunity.profit_pct)
    ordering = column.asc() if direction == "asc" else column.desc()
    page_stmt = stmt.options(
        selectinload(ArbitrageOpportunity.item),
        selectinload(ArbitrageOpportunity.buy_site),
        selectinload(ArbitrageOpportunity.sell_site),
    ).order_by(ordering)
    rows = list(
        (await db.execute(page_stmt.offset((page - 1) * page_size).limit(page_size)))
        .scalars()
        .all()
    )
    return Page(
        items=[opportunity_out(row) for row in rows],
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )


async def list_opportunities_for_item(db: AsyncSession, item_id: int) -> list[OpportunityOut]:
    stmt = apply_filters(
        _base_stmt(),
        q=None,
        weapon=None,
        wear=None,
        stattrak=None,
        souvenir=None,
        min_profit=None,
        min_profit_pct=None,
        min_liquidity=None,
        buy_ids=[],
        sell_ids=[],
        exclude_ids=[],
        instant_only=False,
        cash_out_only=False,
    )
    stmt = stmt.where(ArbitrageOpportunity.item_id == item_id)
    stmt = stmt.options(
        selectinload(ArbitrageOpportunity.item),
        selectinload(ArbitrageOpportunity.buy_site),
        selectinload(ArbitrageOpportunity.sell_site),
    )
    rows = list(
        (await db.execute(stmt.order_by(ArbitrageOpportunity.profit_pct.desc()))).scalars().all()
    )
    return [opportunity_out(row) for row in rows]
