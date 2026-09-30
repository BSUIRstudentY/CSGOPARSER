"""One polling cycle: fetch every enabled marketplace, then recompute spreads."""

from datetime import UTC, datetime
from decimal import Decimal

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import FxRate, ParserRun, Site
from app.services.cache import PriceCache
from app.services.demo_data import listings_for_site
from app.services.ingest import ingest_listings
from app.services.opportunities import recompute_opportunities
from app.services.parsers.base import Listing, ParserError, SiteContext, filter_listings
from app.services.parsers.registry import get_parser

log = get_logger("cycle")


async def run_cycle(
    factory: async_sessionmaker[AsyncSession],
    cache: PriceCache,
) -> None:
    async with factory() as session:
        site_rows = await session.execute(select(Site).where(Site.enabled.is_(True)))
        sites = list(site_rows.scalars().all())
        rates = await _rates(session)
        site_ids = [site.id for site in sites]

    for site_id in site_ids:
        async with factory() as session:
            site = await session.get(Site, site_id)
            if site is None or not site.enabled:
                continue
            await run_site(session, site, rates, cache)

    async with factory() as session:
        stored = await recompute_opportunities(
            session, Decimal(str(get_settings().arb_min_store_pct))
        )
    log.info("cycle_complete", sites=len(site_ids), opportunities=stored)


async def run_site_by_slug(
    factory: async_sessionmaker[AsyncSession],
    cache: PriceCache,
    slug: str,
) -> None:
    async with factory() as session:
        result = await session.execute(select(Site).where(Site.slug == slug))
        site = result.scalar_one_or_none()
        if site is None:
            log.error("parser_missing_site", slug=slug)
            return
        rates = await _rates(session)
        await run_site(session, site, rates, cache, ignore_interval=True)
    async with factory() as session:
        await recompute_opportunities(session, Decimal(str(get_settings().arb_min_store_pct)))


async def run_site(
    session: AsyncSession,
    site: Site,
    rates: dict[str, Decimal],
    cache: PriceCache,
    *,
    ignore_interval: bool = False,
) -> None:
    now = datetime.now(UTC)
    site_id = site.id
    slug = site.slug
    if not ignore_interval and await _within_min_interval(session, site, now):
        log.info("parser_skipped_interval", site=slug)
        return
    started = now
    try:
        listings = await collect_listings(site)
        stats = await ingest_listings(session, site, listings, rates, cache)
        session.add(
            ParserRun(
                site_id=site_id,
                started_at=started,
                finished_at=datetime.now(UTC),
                status="success",
                items_fetched=stats.fetched,
                items_upserted=stats.prices_written,
                error=None,
            )
        )
        await session.commit()
        log.info(
            "parser_success",
            site=slug,
            fetched=stats.fetched,
            written=stats.prices_written,
            created=stats.items_created,
            review=stats.needs_review,
        )
    except Exception as exc:
        await session.rollback()
        message = str(exc)[:4000]
        log.error("parser_failed", site=slug, error=message)
        session.add(
            ParserRun(
                site_id=site_id,
                started_at=started,
                finished_at=datetime.now(UTC),
                status="failed",
                items_fetched=0,
                items_upserted=0,
                error=message,
            )
        )
        await session.commit()


async def collect_listings(site: Site, query: str | None = None) -> list[Listing]:
    settings = get_settings()
    if settings.parser_mode == "demo":
        tick = int(datetime.now(UTC).timestamp() // 3600)
        rows = listings_for_site(site.slug, tick)
        return filter_listings(rows, query) if query else rows

    if site.tos_restricted and not (site.config or {}).get("allow_restricted", False):
        raise ParserError(
            f"{site.name} is flagged as restricted. It stays disabled unless you set "
            "config.allow_restricted after confirming the marketplace allows this access. "
            "This project does not bypass bot protection or scrape forbidden pages."
        )
    parser = get_parser(site.slug)
    if parser is None:
        raise ParserError(f"No parser registered for {site.slug}")

    timeout = float((site.config or {}).get("timeout_seconds") or settings.http_timeout_seconds)
    context = SiteContext(
        slug=site.slug,
        base_url=site.base_url,
        currency=site.currency,
        config=dict(site.config or {}),
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), follow_redirects=True) as client:
        if query:
            return await parser.search(context, client, query)
        return await parser.fetch(context, client)


async def _rates(session: AsyncSession) -> dict[str, Decimal]:
    result = await session.execute(select(FxRate))
    return {row.currency.upper(): row.usd_per_unit for row in result.scalars().all()}


async def _within_min_interval(session: AsyncSession, site: Site, now: datetime) -> bool:
    interval = int((site.config or {}).get("min_interval_seconds") or 0)
    if interval <= 0:
        return False
    result = await session.execute(
        select(ParserRun)
        .where(ParserRun.site_id == site.id, ParserRun.status == "success")
        .order_by(ParserRun.finished_at.desc())
        .limit(1)
    )
    last = result.scalar_one_or_none()
    if last is None or last.finished_at is None:
        return False
    finished = last.finished_at
    if finished.tzinfo is None:
        finished = finished.replace(tzinfo=UTC)
    return (now - finished).total_seconds() < interval
