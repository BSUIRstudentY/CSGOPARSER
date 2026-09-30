"""Admin operations: parser runs, manual mapping, FX."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db, money, require_admin
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import FxRate, Item, ItemAlias, ParserRun, Site, User
from app.schemas.common import FxRateOut, FxRateUpdate
from app.schemas.market import AliasLink, AliasOut, ParserRunOut, StatsOut
from app.services.cycle import run_site_by_slug

router = APIRouter(tags=["admin"])
log = get_logger("admin")


def _run_out(row: ParserRun) -> ParserRunOut:
    return ParserRunOut(
        id=row.id,
        site=row.site.slug,
        started_at=row.started_at,
        finished_at=row.finished_at,
        status=row.status,
        items_fetched=row.items_fetched,
        items_upserted=row.items_upserted,
        error=row.error,
    )


@router.get("/stats", response_model=StatsOut)
async def stats(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> StatsOut:
    return await build_stats(db)


async def build_stats(db: AsyncSession) -> StatsOut:
    from app.db.models import ArbitrageOpportunity

    items = await db.scalar(select(func.count()).select_from(Item))
    opportunities = await db.scalar(select(func.count()).select_from(ArbitrageOpportunity))
    best = (
        await db.execute(
            select(ArbitrageOpportunity.profit_usd, ArbitrageOpportunity.profit_pct)
            .where(ArbitrageOpportunity.is_active.is_(True))
            .order_by(ArbitrageOpportunity.profit_usd.desc())
            .limit(1)
        )
    ).first()
    enabled = await db.scalar(select(func.count()).select_from(Site).where(Site.enabled.is_(True)))
    runs = (
        (
            await db.execute(
                select(ParserRun)
                .options(selectinload(ParserRun.site))
                .order_by(ParserRun.id.desc())
                .limit(8)
            )
        )
        .scalars()
        .all()
    )
    return StatsOut(
        items=int(items or 0),
        opportunities=int(opportunities or 0),
        best_profit_usd=money(best[0]) if best else None,
        best_profit_pct=money(best[1]) if best else None,
        parser_mode=get_settings().parser_mode,
        sites_enabled=int(enabled or 0),
        last_runs=[_run_out(row) for row in runs],
    )


@router.get("/admin/parser-runs", response_model=list[ParserRunOut])
async def parser_runs(
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[ParserRunOut]:
    rows = (
        (
            await db.execute(
                select(ParserRun)
                .options(selectinload(ParserRun.site))
                .order_by(ParserRun.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [_run_out(row) for row in rows]


@router.post("/admin/parsers/{slug}/run", status_code=202)
async def run_parser(
    slug: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict[str, str]:
    result = await db.execute(select(Site).where(Site.slug == slug))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Marketplace not found")
    factory = request.app.state.session_factory
    cache = request.app.state.cache

    async def _task() -> None:
        try:
            await run_site_by_slug(factory, cache, slug)
        except Exception as exc:
            log.error("manual_parser_failed", slug=slug, error=str(exc))

    asyncio.create_task(_task())
    return {"status": "started", "slug": slug}


@router.get("/admin/aliases", response_model=list[AliasOut])
async def aliases(
    needs_review: bool = True,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[AliasOut]:
    stmt = select(ItemAlias).options(selectinload(ItemAlias.site)).order_by(ItemAlias.id.desc())
    if needs_review:
        stmt = stmt.where(ItemAlias.needs_review.is_(True))
    rows = (await db.execute(stmt.limit(200))).scalars().all()
    return [
        AliasOut(
            id=row.id,
            site=row.site.slug,
            raw_name=row.raw_name,
            normalized_key=row.normalized_key,
            match_method=row.match_method,
            confidence=money(row.confidence),
            needs_review=row.needs_review,
            item_id=row.item_id,
            suggested_item_id=row.suggested_item_id,
        )
        for row in rows
    ]


@router.post("/admin/aliases/{alias_id}/link", response_model=AliasOut)
async def link_alias(
    alias_id: int,
    payload: AliasLink,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> AliasOut:
    alias = await db.get(ItemAlias, alias_id)
    if alias is None:
        raise HTTPException(status_code=404, detail="Alias not found")
    item = await db.get(Item, payload.item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    alias.item_id = item.id
    alias.suggested_item_id = item.id
    alias.needs_review = False
    alias.match_method = "manual"
    alias.confidence = Decimal("1")
    await db.commit()
    await db.refresh(alias, attribute_names=["site"])
    return AliasOut(
        id=alias.id,
        site=alias.site.slug,
        raw_name=alias.raw_name,
        normalized_key=alias.normalized_key,
        match_method=alias.match_method,
        confidence=1,
        needs_review=False,
        item_id=alias.item_id,
        suggested_item_id=alias.suggested_item_id,
    )


@router.get("/fx", response_model=list[FxRateOut])
async def list_fx(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[FxRateOut]:
    rows = (await db.execute(select(FxRate).order_by(FxRate.currency))).scalars().all()
    return [FxRateOut(currency=row.currency, usd_per_unit=money(row.usd_per_unit)) for row in rows]


@router.put("/admin/fx/{currency}", response_model=FxRateOut)
async def update_fx(
    currency: str,
    payload: FxRateUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> FxRateOut:
    code = currency.upper()
    row = await db.get(FxRate, code)
    if row is None:
        row = FxRate(currency=code, usd_per_unit=Decimal(str(payload.usd_per_unit)))
        db.add(row)
    else:
        row.usd_per_unit = Decimal(str(payload.usd_per_unit))
    row.updated_at = datetime.now(UTC)
    await db.commit()
    return FxRateOut(currency=code, usd_per_unit=payload.usd_per_unit)
