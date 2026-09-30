"""Turn raw listings into canonical items, aliases, and price history."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Item, ItemAlias, Price, Site
from app.services.arbitrage import as_decimal
from app.services.cache import PriceCache
from app.services.fx import UnknownCurrencyError, to_usd
from app.services.normalization import CatalogMatcher, parse_market_hash_name
from app.services.parsers.base import Listing, aggregate_listings


@dataclass
class IngestStats:
    fetched: int = 0
    prices_written: int = 0
    items_created: int = 0
    needs_review: int = 0
    skipped_unchanged: int = 0
    skipped_currency: int = 0


async def ingest_listings(
    session: AsyncSession,
    site: Site,
    listings: list[Listing],
    rates: dict[str, Decimal],
    cache: PriceCache | None = None,
    *,
    captured_at: datetime | None = None,
) -> IngestStats:
    settings = get_settings()
    stats = IngestStats(fetched=len(listings))
    rows = aggregate_listings(listings)
    when = captured_at or datetime.now(UTC)

    item_result = await session.execute(select(Item))
    items = list(item_result.scalars().all())
    by_key = {item.match_key: item for item in items}
    by_id = {item.id: item for item in items}

    alias_result = await session.execute(select(ItemAlias).where(ItemAlias.site_id == site.id))
    aliases = {alias.raw_name: alias for alias in alias_result.scalars().all()}

    price_result = await session.execute(
        select(Price)
        .where(Price.site_id == site.id)
        .order_by(Price.captured_at.desc(), Price.id.desc())
    )
    latest: dict[int, Price] = {}
    for price in price_result.scalars().all():
        latest.setdefault(price.item_id, price)

    matcher = CatalogMatcher(
        list(by_key),
        auto_threshold=settings.fuzzy_auto_threshold,
        review_threshold=settings.fuzzy_review_threshold,
        fuzzy_budget=settings.fuzzy_budget_per_cycle,
    )

    for listing in rows:
        item = _resolve_item(
            session,
            site,
            listing,
            aliases,
            by_key,
            by_id,
            matcher,
            stats,
        )
        if item is None:
            continue
        # New catalog rows need a primary key before the price row can reference them.
        if item.id is None:
            await session.flush()
        by_id[item.id] = item
        try:
            usd = to_usd(listing.price, listing.currency, rates)
        except UnknownCurrencyError:
            stats.skipped_currency += 1
            continue
        previous = latest.get(item.id)
        count = listing.listings_count
        if previous is not None and _same_quote(previous, usd, count):
            stats.skipped_unchanged += 1
            continue
        price = Price(
            item_id=item.id,
            site_id=site.id,
            price=listing.price,
            price_usd=usd,
            currency=listing.currency.upper(),
            listings_count=count,
            volume_24h=listing.volume_24h,
            captured_at=when,
            details={k: v for k, v in listing.metadata.items() if v is not None},
        )
        session.add(price)
        latest[item.id] = price
        stats.prices_written += 1
        if cache is not None:
            await cache.put_quote(
                item.id,
                site.slug,
                {
                    "site": site.slug,
                    "price": float(listing.price),
                    "price_usd": float(usd),
                    "currency": listing.currency.upper(),
                    "listings_count": count,
                    "captured_at": when.isoformat(),
                },
            )
    await session.commit()
    return stats


def _resolve_item(
    session: AsyncSession,
    site: Site,
    listing: Listing,
    aliases: dict[str, ItemAlias],
    by_key: dict[str, Item],
    by_id: dict[int, Item],
    matcher: CatalogMatcher,
    stats: IngestStats,
) -> Item | None:
    existing = aliases.get(listing.raw_name)
    if existing is not None and existing.item_id is not None and not existing.needs_review:
        found = by_id.get(existing.item_id)
        if found is not None:
            return found

    parsed = parse_market_hash_name(listing.raw_name)
    if parsed is None:
        _upsert_alias(
            session,
            aliases,
            site_id=site.id,
            raw_name=listing.raw_name,
            normalized_key="",
            method="unparsed",
            confidence=Decimal("0"),
            needs_review=True,
            item=None,
            suggested=None,
            external_id=listing.external_id,
        )
        stats.needs_review += 1
        return None

    decision = matcher.match(parsed)
    if decision.needs_review:
        suggested = by_key.get(decision.item_key or "")
        _upsert_alias(
            session,
            aliases,
            site_id=site.id,
            raw_name=listing.raw_name,
            normalized_key=parsed.match_key,
            method=decision.method,
            confidence=Decimal(str(round(decision.confidence, 4))),
            needs_review=True,
            item=None,
            suggested=suggested,
            external_id=listing.external_id,
        )
        stats.needs_review += 1
        return None

    if decision.create_new:
        item = Item(
            game="CS2",
            weapon=parsed.weapon,
            skin_name=parsed.skin_name,
            wear=parsed.wear,
            stattrak=parsed.stattrak,
            souvenir=parsed.souvenir,
            canonical_name=parsed.canonical_name,
            match_key=parsed.match_key,
        )
        session.add(item)
        # flush happens with the commit batch; assign a temporary identity via flush in caller.
        # We flush here so later listings in this batch can link to the new row.
        by_key[parsed.match_key] = item
        matcher.add_key(parsed.match_key)
        stats.items_created += 1
        method = "created"
        confidence = Decimal("1")
    else:
        item = by_key[decision.item_key or ""]
        method = decision.method
        confidence = Decimal(str(round(decision.confidence, 4)))

    _upsert_alias(
        session,
        aliases,
        site_id=site.id,
        raw_name=listing.raw_name,
        normalized_key=parsed.match_key,
        method=method,
        confidence=confidence,
        needs_review=False,
        item=item,
        suggested=None,
        external_id=listing.external_id,
    )
    return item


def _upsert_alias(
    session: AsyncSession,
    aliases: dict[str, ItemAlias],
    *,
    site_id: int,
    raw_name: str,
    normalized_key: str,
    method: str,
    confidence: Decimal,
    needs_review: bool,
    item: Item | None,
    suggested: Item | None,
    external_id: str | None,
) -> None:
    alias = aliases.get(raw_name)
    if alias is None:
        alias = ItemAlias(
            site_id=site_id,
            raw_name=raw_name,
            normalized_key=normalized_key,
            match_method=method,
            confidence=confidence,
            needs_review=needs_review,
            external_id=external_id,
        )
        alias.item = item
        if suggested is not None and suggested.id is not None:
            alias.suggested_item_id = suggested.id
        session.add(alias)
        aliases[raw_name] = alias
        return
    alias.normalized_key = normalized_key
    alias.match_method = method
    alias.confidence = confidence
    alias.needs_review = needs_review
    alias.external_id = external_id or alias.external_id
    if item is not None:
        alias.item = item
        alias.needs_review = False
    if suggested is not None and suggested.id is not None:
        alias.suggested_item_id = suggested.id


def _same_quote(previous: Price, usd: Decimal, count: int | None) -> bool:
    previous_usd = as_decimal(previous.price_usd).quantize(Decimal("0.0001"))
    return previous_usd == usd.quantize(Decimal("0.0001")) and previous.listings_count == count
