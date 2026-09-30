"""Marketplace directory."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_admin, site_out
from app.db.models import Site, User
from app.schemas.market import ListingSearchOut, SiteOut, SiteUpdate
from app.services.cycle import collect_listings
from app.services.parsers.base import ParserError

router = APIRouter(prefix="/sites", tags=["sites"])

_MONEY = {
    "buy_fee_pct",
    "sell_fee_pct",
    "deposit_fee_pct",
    "deposit_fee_flat",
    "withdraw_fee_pct",
    "withdraw_fee_flat",
}


@router.get("", response_model=list[SiteOut])
async def list_sites(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[SiteOut]:
    rows = (await db.execute(select(Site).order_by(Site.name))).scalars().all()
    return [site_out(row) for row in rows]


@router.get("/{slug}/search", response_model=list[ListingSearchOut])
async def search_site(
    slug: str,
    q: str = Query(min_length=2),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ListingSearchOut]:
    result = await db.execute(select(Site).where(Site.slug == slug))
    site = result.scalar_one_or_none()
    if site is None:
        raise HTTPException(status_code=404, detail="Marketplace not found")
    if not site.enabled:
        raise HTTPException(status_code=409, detail="Marketplace is disabled")
    try:
        listings = await collect_listings(site, query=q)
    except ParserError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [
        ListingSearchOut(
            raw_name=row.raw_name,
            price=float(row.price),
            currency=row.currency,
            listings_count=row.listings_count,
        )
        for row in listings[:50]
    ]


@router.patch("/{site_id}", response_model=SiteOut)
async def update_site(
    site_id: int,
    payload: SiteUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> SiteOut:
    site = await db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=404, detail="Marketplace not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        if key in _MONEY and value is not None:
            value = Decimal(str(value))
        setattr(site, key, value)
    await db.commit()
    await db.refresh(site)
    return site_out(site)
