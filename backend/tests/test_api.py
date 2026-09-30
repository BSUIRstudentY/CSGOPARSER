"""API flows: auth, ingest, arbitrage filters, alerts."""

from decimal import Decimal

import pytest
from app.db.models import FxRate, Site
from app.main import app
from app.services.ingest import ingest_listings
from app.services.opportunities import recompute_opportunities
from app.services.parsers.base import Listing
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import auth_header, promote

pytestmark = pytest.mark.asyncio

NAME = "AK-47 | Redline (Field-Tested)"


async def _prepare(session: AsyncSession) -> None:
    session.add(FxRate(currency="USD", usd_per_unit=Decimal("1")))
    session.add(
        Site(
            slug="dmarket",
            name="DMarket",
            base_url="https://api.dmarket.com",
            currency="USD",
            buy_fee_pct=Decimal("0"),
            sell_fee_pct=Decimal("0"),
            deposit_fee_pct=Decimal("0"),
            deposit_fee_flat=Decimal("0"),
            withdraw_fee_pct=Decimal("0"),
            withdraw_fee_flat=Decimal("0"),
            trade_lock_days=0,
            cash_out=True,
            enabled=True,
            tos_restricted=False,
            payment_methods=["balance"],
            config={},
        )
    )
    session.add(
        Site(
            slug="skinport",
            name="Skinport",
            base_url="https://api.skinport.com",
            currency="USD",
            buy_fee_pct=Decimal("0"),
            sell_fee_pct=Decimal("0.10"),
            deposit_fee_pct=Decimal("0"),
            deposit_fee_flat=Decimal("0"),
            withdraw_fee_pct=Decimal("0"),
            withdraw_fee_flat=Decimal("0"),
            trade_lock_days=0,
            cash_out=True,
            enabled=True,
            tos_restricted=False,
            payment_methods=["balance"],
            config={},
        )
    )
    session.add(
        Site(
            slug="steam",
            name="Steam Market",
            base_url="https://steamcommunity.com",
            currency="USD",
            buy_fee_pct=Decimal("0"),
            sell_fee_pct=Decimal("0.1304"),
            deposit_fee_pct=Decimal("0"),
            deposit_fee_flat=Decimal("0"),
            withdraw_fee_pct=Decimal("0"),
            withdraw_fee_flat=Decimal("0"),
            trade_lock_days=7,
            cash_out=False,
            enabled=True,
            tos_restricted=False,
            payment_methods=["steam_wallet"],
            config={},
        )
    )
    await session.commit()
    sites = {row.slug: row for row in (await session.execute(select(Site))).scalars().all()}
    rates = {"USD": Decimal("1")}
    await ingest_listings(
        session,
        sites["dmarket"],
        [Listing(NAME, Decimal("100"), "USD", listings_count=20, bid=Decimal("70"))],
        rates,
    )
    sites = {row.slug: row for row in (await session.execute(select(Site))).scalars().all()}
    await ingest_listings(
        session,
        sites["skinport"],
        [Listing(NAME, Decimal("150"), "USD", listings_count=11, bid=Decimal("140"))],
        rates,
    )
    sites = {row.slug: row for row in (await session.execute(select(Site))).scalars().all()}
    await ingest_listings(
        session,
        sites["steam"],
        [Listing(NAME, Decimal("120"), "USD", listings_count=30, bid=Decimal("90"))],
        rates,
    )
    await recompute_opportunities(session, Decimal("0"))


async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] is True
    assert body["parser_mode"] == "demo"


async def test_arbitrage_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/arbitrage")
    assert response.status_code == 401


async def test_buy_low_sell_high_after_fees(client: AsyncClient) -> None:
    async with app.state.session_factory() as session:
        await _prepare(session)
    headers = await auth_header(client)
    response = await client.get(
        "/arbitrage", headers=headers, params={"sort": "profit", "direction": "desc"}
    )
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] >= 1
    best = page["items"][0]
    assert best["canonical_name"] == NAME
    assert best["buy_site"] == "dmarket"
    assert best["sell_site"] == "skinport"
    assert best["profit_usd"] == pytest.approx(35.0)
    assert best["profit_pct"] == pytest.approx(35.0)
    assert best["liquidity"] == 11
    assert best["instant_trade"] is True
    assert best["cash_out"] is True

    locked = await client.get("/arbitrage", headers=headers, params={"buy_site": "steam"})
    assert locked.status_code == 200
    steam_rows = locked.json()["items"]
    assert steam_rows
    assert all(row["instant_trade"] is False for row in steam_rows)
    assert all(row["trade_lock_days"] == 7 for row in steam_rows)

    instant = await client.get(
        "/arbitrage", headers=headers, params={"instant_only": True, "cash_out_only": True}
    )
    assert all(row["buy_site"] != "steam" for row in instant.json()["items"])
    assert all(row["cash_out"] is True for row in instant.json()["items"])


async def test_market_ranks_by_price_gap(client: AsyncClient) -> None:
    async with app.state.session_factory() as session:
        await _prepare(session)
    async with app.state.session_factory() as session:
        session.add(
            Site(
                slug="waxpeer",
                name="Waxpeer",
                base_url="https://api.waxpeer.com",
                currency="USD",
                buy_fee_pct=Decimal("0"),
                sell_fee_pct=Decimal("0"),
                deposit_fee_pct=Decimal("0"),
                deposit_fee_flat=Decimal("0"),
                withdraw_fee_pct=Decimal("0"),
                withdraw_fee_flat=Decimal("0"),
                trade_lock_days=0,
                cash_out=True,
                enabled=True,
                tos_restricted=False,
                payment_methods=["balance"],
                config={},
            )
        )
        await session.commit()
        sites = {row.slug: row for row in (await session.execute(select(Site))).scalars().all()}
        await ingest_listings(
            session,
            sites["waxpeer"],
            [Listing(NAME, Decimal("80"), "USD", listings_count=4)],
            {"USD": Decimal("1")},
        )
    headers = await auth_header(client, "market@localhost")
    response = await client.get("/market", headers=headers, params={"q": "Redline"})
    assert response.status_code == 200, response.text
    card = response.json()["items"][0]
    # Cards compare buy orders (70 / 90 / 140), not the cheapest listings (100 / 120 / 150).
    assert card["cheapest"]["site"] == "dmarket"
    assert card["cheapest"]["price_usd"] == pytest.approx(70)
    assert card["highest"]["site"] == "skinport"
    assert card["highest"]["price_usd"] == pytest.approx(140)
    assert card["spread_usd"] == pytest.approx(70)
    assert card["cheapest"]["url"].startswith("https://dmarket.com/")
    assert "waxpeer" not in {quote["site"] for quote in card["quotes"]}
    steam = next(quote for quote in card["quotes"] if quote["site"] == "steam")
    assert steam["url"].startswith("https://steamcommunity.com/market/listings/730/")


async def test_item_history_and_alert(client: AsyncClient) -> None:
    async with app.state.session_factory() as session:
        await _prepare(session)
    headers = await auth_header(client, "other@localhost")
    items = await client.get("/items", headers=headers, params={"q": "Redline"})
    assert items.status_code == 200
    item_id = items.json()["items"][0]["id"]

    history = await client.get(f"/items/{item_id}/prices", headers=headers)
    assert history.status_code == 200
    assert {point["site"] for point in history.json()} == {"dmarket", "skinport", "steam"}

    created = await client.post(
        "/alerts",
        headers=headers,
        json={
            "name": "Redline spread",
            "channel": "telegram",
            "enabled": True,
            "filters": {"q": "Redline", "min_profit_pct": 5, "instant_only": True},
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["delivery"] == "stored_only"
    listed = await client.get("/alerts", headers=headers)
    assert listed.json()[0]["name"] == "Redline spread"


async def test_viewer_cannot_edit_fees_admin_can(client: AsyncClient) -> None:
    async with app.state.session_factory() as session:
        await _prepare(session)
    headers = await auth_header(client, "viewer@localhost")
    sites = await client.get("/sites", headers=headers)
    site_id = next(row["id"] for row in sites.json() if row["slug"] == "skinport")
    denied = await client.patch(f"/sites/{site_id}", headers=headers, json={"sell_fee_pct": 0.06})
    assert denied.status_code == 403

    async with app.state.session_factory() as session:
        await promote(session, "viewer@localhost")
    # The old token was issued before promotion; log in again.
    login = await client.post(
        "/auth/login", json={"email": "viewer@localhost", "password": "supersecret"}
    )
    admin_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    updated = await client.patch(
        f"/sites/{site_id}", headers=admin_headers, json={"sell_fee_pct": 0.06}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["sell_fee_pct"] == pytest.approx(0.06)
    assert updated.json()["secret_configured"] is False
