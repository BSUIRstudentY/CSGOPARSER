"""Idempotent startup data: marketplaces, FX, an admin user, and demo history."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.security import hash_password
from app.db.base import Base
from app.db.models import FxRate, Price, Site, User, UserSettings
from app.db.session import make_engine
from app.services.demo_data import history_ticks, listings_for_site
from app.services.ingest import ingest_listings
from app.services.opportunities import recompute_opportunities

log = get_logger("seed")

DEFAULT_FX: dict[str, str] = {
    "USD": "1",
    "EUR": "1.08",
    "GBP": "1.27",
    "CNY": "0.14",
    "RUB": "0.011",
}

# Fees are fractions (0.12 = 12%) and are defaults, not a live fee schedule.
# Edit them in the admin page after checking each marketplace.
DEFAULT_SITES: list[dict[str, Any]] = [
    {
        "slug": "skinport",
        "name": "Skinport",
        "base_url": "https://api.skinport.com",
        "currency": "USD",
        "buy_fee_pct": "0",
        "sell_fee_pct": "0.12",
        "deposit_fee_pct": "0",
        "deposit_fee_flat": "0",
        "withdraw_fee_pct": "0",
        "withdraw_fee_flat": "0",
        "trade_lock_days": 0,
        "cash_out": True,
        "enabled": True,
        "tos_restricted": False,
        "payment_methods": ["balance", "card", "crypto"],
        "config": {
            "currency": "USD",
            "tradable": True,
            "min_interval_seconds": 300,
            "timeout_seconds": 60,
        },
        "notes": (
            "Official public API GET /v1/items. No key. Limit 8 requests per 5 minutes; "
            "Brotli is required. Seller fee default is 12% (lower with Skinport Plus). "
            "The listed min price is what the buyer pays. tradable=true keeps the tradable cohort. "
            "If a withdrawal still carries a Steam hold, raise trade_lock_days. "
            "A Cloudflare challenge is reported as a failed run and is not bypassed."
        ),
    },
    {
        "slug": "dmarket",
        "name": "DMarket",
        "base_url": "https://api.dmarket.com",
        "currency": "USD",
        "buy_fee_pct": "0",
        "sell_fee_pct": "0.07",
        "deposit_fee_pct": "0",
        "deposit_fee_flat": "0",
        "withdraw_fee_pct": "0",
        "withdraw_fee_flat": "0",
        "trade_lock_days": 0,
        "cash_out": True,
        "enabled": True,
        "tos_restricted": False,
        "payment_methods": ["balance", "card", "crypto"],
        "secret_env": "DMARKET_SECRET_KEY",
        "config": {
            "game_id": "a8db",
            "max_pages": 25,
            "page_limit": 100,
            "min_interval_seconds": 60,
            "timeout_seconds": 45,
        },
        "notes": (
            "Official marketplace-api/v2/offers. Prices are integer cents. "
            "gameId a8db is CS2. Requires DMARKET_PUBLIC_KEY and DMARKET_SECRET_KEY; "
            "the old unsigned /exchange/v1/market/items route is retired. "
            "Default seller fee is 7%; confirm it in DMarket before trading. "
            "max_pages is 25 (2,500 offers). Steam stays smaller until a separate decision."
        ),
    },
    {
        "slug": "waxpeer",
        "name": "Waxpeer",
        "base_url": "https://api.waxpeer.com",
        "currency": "USD",
        "buy_fee_pct": "0",
        "sell_fee_pct": "0.02",
        "deposit_fee_pct": "0",
        "deposit_fee_flat": "0",
        "withdraw_fee_pct": "0",
        "withdraw_fee_flat": "0",
        "trade_lock_days": 0,
        "cash_out": True,
        "enabled": True,
        "tos_restricted": False,
        "payment_methods": ["balance", "crypto"],
        "config": {"game": "csgo", "min_interval_seconds": 300, "timeout_seconds": 120},
        "notes": (
            "Official public price list GET /v1/prices?game=csgo. "
            "The min field is thousandths of a dollar (1000 = $1). "
            "Default seller fee is 2%; confirm the current Waxpeer commission."
        ),
    },
    {
        "slug": "steam",
        "name": "Steam Market",
        "base_url": "https://steamcommunity.com",
        "currency": "USD",
        "buy_fee_pct": "0",
        "sell_fee_pct": "0.1304",
        "deposit_fee_pct": "0",
        "deposit_fee_flat": "0",
        "withdraw_fee_pct": "0",
        "withdraw_fee_flat": "0",
        "trade_lock_days": 7,
        "cash_out": False,
        "enabled": True,
        "tos_restricted": False,
        "payment_methods": ["steam_wallet"],
        "config": {
            "max_pages": 2,
            "page_size": 100,
            "page_delay_seconds": 1.5,
            "min_interval_seconds": 300,
            "timeout_seconds": 30,
        },
        "notes": (
            "Community Market search JSON (currency=1, USD), not a partner price API. "
            "Partial on purpose: max_pages stays at 2 until a separate decision to widen it. "
            "sell_price is the buyer-facing price, so buy_fee is 0. "
            "A sale returns about 86.96% to the Steam wallet (13.04% combined fee) and "
            "that balance cannot be withdrawn as cash. Purchased items are trade-locked for 7 days."
        ),
    },
    {
        "slug": "market_csgo",
        "name": "Market.CSGO",
        "base_url": "https://market.csgo.com",
        "currency": "USD",
        "buy_fee_pct": "0",
        "sell_fee_pct": "0.05",
        "deposit_fee_pct": "0",
        "deposit_fee_flat": "0",
        "withdraw_fee_pct": "0",
        "withdraw_fee_flat": "0",
        "trade_lock_days": 7,
        "cash_out": True,
        "enabled": True,
        "tos_restricted": False,
        "payment_methods": ["balance", "card"],
        "config": {"min_interval_seconds": 300, "timeout_seconds": 60},
        "notes": (
            "Official public price export GET /api/v2/prices/USD.json. "
            "Default seller commission is 5%. Purchases settled by a Steam trade are often "
            "locked for 7 days; set trade_lock_days to 0 if you only count tradable stock."
        ),
    },
]


async def seed(session: AsyncSession) -> None:
    settings = get_settings()
    await _seed_fx(session)
    sites = await _seed_sites(session)
    await _seed_admin(
        session, settings.admin_email, settings.admin_password, settings.seed_demo_user
    )
    await session.commit()
    if settings.parser_mode == "demo":
        await _seed_demo_prices(session, sites)
    price_count = await session.scalar(select(func.count()).select_from(Price))
    if price_count:
        stored = await recompute_opportunities(session, Decimal(str(settings.arb_min_store_pct)))
        log.info("opportunities_seeded", count=stored)


async def _seed_fx(session: AsyncSession) -> None:
    existing = set((await session.execute(select(FxRate.currency))).scalars().all())
    now = datetime.now(UTC)
    for code, rate in DEFAULT_FX.items():
        if code in existing:
            continue
        session.add(FxRate(currency=code, usd_per_unit=Decimal(rate), updated_at=now))


async def _seed_sites(session: AsyncSession) -> list[Site]:
    result = await session.execute(select(Site))
    by_slug = {site.slug: site for site in result.scalars().all()}
    for spec in DEFAULT_SITES:
        if spec["slug"] in by_slug:
            continue
        site = Site(
            slug=spec["slug"],
            name=spec["name"],
            base_url=spec["base_url"],
            currency=spec["currency"],
            buy_fee_pct=Decimal(spec["buy_fee_pct"]),
            sell_fee_pct=Decimal(spec["sell_fee_pct"]),
            deposit_fee_pct=Decimal(spec["deposit_fee_pct"]),
            deposit_fee_flat=Decimal(spec["deposit_fee_flat"]),
            withdraw_fee_pct=Decimal(spec["withdraw_fee_pct"]),
            withdraw_fee_flat=Decimal(spec["withdraw_fee_flat"]),
            trade_lock_days=spec["trade_lock_days"],
            cash_out=spec["cash_out"],
            enabled=spec["enabled"],
            tos_restricted=spec["tos_restricted"],
            payment_methods=list(spec["payment_methods"]),
            config=dict(spec["config"]),
            secret_env=spec.get("secret_env"),
            notes=spec["notes"],
        )
        session.add(site)
        by_slug[site.slug] = site
    await session.flush()
    return list(by_slug.values())


async def _seed_admin(session: AsyncSession, email: str, password: str, enabled: bool) -> None:
    if not enabled or not email or not password:
        return
    normalized = email.strip().lower()
    result = await session.execute(select(User).where(User.email == normalized))
    if result.scalar_one_or_none() is not None:
        return
    user = User(email=normalized, password_hash=hash_password(password), is_admin=True)
    session.add(user)
    await session.flush()
    session.add(
        UserSettings(
            user_id=user.id,
            default_filters={
                "min_profit_pct": 1,
                "min_liquidity": 5,
                "instant_only": False,
                "cash_out_only": True,
            },
        )
    )
    log.info("admin_seeded", email=normalized)


async def _seed_demo_prices(session: AsyncSession, sites: list[Site]) -> None:
    count = await session.scalar(select(func.count()).select_from(Price))
    if count:
        return
    rate_rows = (await session.execute(select(FxRate))).scalars().all()
    rates = {row.currency: row.usd_per_unit for row in rate_rows}
    enabled = [site for site in sites if site.enabled]
    for captured_at, tick in history_ticks(14):
        for site in enabled:
            # Re-load so each ingest sees a session-bound site after the previous commit.
            bound = await session.get(Site, site.id)
            if bound is None:
                continue
            await ingest_listings(
                session,
                bound,
                listings_for_site(bound.slug, tick),
                rates,
                cache=None,
                captured_at=captured_at,
            )
    log.info("demo_prices_seeded", sites=len(enabled))


async def main() -> None:
    setup_logging()
    settings = get_settings()
    engine = make_engine(settings.database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    if settings.database_url.startswith("sqlite"):
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
    async with factory() as session:
        await seed(session)
    await engine.dispose()
    log.info("seed_complete", parser_mode=settings.parser_mode)


if __name__ == "__main__":
    asyncio.run(main())
