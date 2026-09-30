from decimal import Decimal

import httpx
import pytest
from app.services.parsers.base import ParserError, SiteContext, aggregate_listings
from app.services.parsers.dmarket import DMarketParser
from app.services.parsers.market_csgo import MarketCsgoParser
from app.services.parsers.skinport import SkinportParser
from app.services.parsers.steam import SteamParser
from app.services.parsers.waxpeer import WaxpeerParser


def _client(handler):  # type: ignore[no-untyped-def]
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _ctx(slug: str, url: str = "https://example.test") -> SiteContext:
    return SiteContext(
        slug=slug, base_url=url, currency="USD", config={"max_pages": 1, "page_size": 100}
    )


@pytest.mark.asyncio
async def test_skinport_parses_min_price() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["currency"] == "USD"
        assert request.headers["accept-encoding"] == "br"
        return httpx.Response(
            200,
            json=[
                {
                    "market_hash_name": "AK-47 | Redline (Field-Tested)",
                    "currency": "EUR",
                    "suggested_price": 20,
                    "min_price": 11.5,
                    "quantity": 8,
                }
            ],
        )

    async with _client(handler) as client:
        rows = await SkinportParser().fetch(_ctx("skinport", "https://api.skinport.com"), client)
    assert rows[0].raw_name.startswith("AK-47")
    assert rows[0].price == Decimal("11.5")
    assert rows[0].currency == "EUR"
    assert rows[0].listings_count == 8


@pytest.mark.asyncio
async def test_skinport_html_challenge_is_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, text="<html>Just a moment</html>", headers={"content-type": "text/html"}
        )

    async with _client(handler) as client:
        with pytest.raises(ParserError, match="does not bypass"):
            await SkinportParser().fetch(_ctx("skinport", "https://api.skinport.com"), client)


@pytest.mark.asyncio
async def test_dmarket_cents_and_offer_counts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["gameId"] == "a8db"
        return httpx.Response(
            200,
            json={
                "objects": [
                    {
                        "title": "AWP | Asiimov (Field-Tested)",
                        "price": {"USD": "6200"},
                        "itemId": "a",
                    },
                    {
                        "title": "AWP | Asiimov (Field-Tested)",
                        "price": {"USD": "6400"},
                        "itemId": "b",
                    },
                ],
                "cursor": "",
            },
        )

    async with _client(handler) as client:
        rows = await DMarketParser().fetch(_ctx("dmarket"), client)
    assert len(rows) == 1
    assert rows[0].price == Decimal("62")
    assert rows[0].listings_count == 2


@pytest.mark.asyncio
async def test_waxpeer_thousandths() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "items": [{"name": "Glock-18 | Fade (Factory New)", "min": 250000, "count": 3}],
            },
        )

    async with _client(handler) as client:
        rows = await WaxpeerParser().fetch(_ctx("waxpeer", "https://api.waxpeer.com"), client)
    assert rows[0].price == Decimal("250")
    assert rows[0].listings_count == 3


@pytest.mark.asyncio
async def test_steam_buyer_price_is_cents() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["currency"] == "1"
        return httpx.Response(
            200,
            json={
                "success": True,
                "results": [
                    {
                        "hash_name": "USP-S | Kill Confirmed (Minimal Wear)",
                        "sell_price": 7250,
                        "sell_listings": 12,
                    }
                ],
            },
        )

    async with _client(handler) as client:
        rows = await SteamParser().fetch(
            _ctx("steam", "https://steamcommunity.com"),
            client,
        )
    assert rows[0].price == Decimal("72.5")
    assert rows[0].listings_count == 12


@pytest.mark.asyncio
async def test_market_csgo_price_file() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "currency": "USD",
                "items": [
                    {
                        "market_hash_name": "M4A1-S | Printstream (Field-Tested)",
                        "price": "210.5",
                        "volume": "15",
                    }
                ],
            },
        )

    async with _client(handler) as client:
        rows = await MarketCsgoParser().fetch(
            _ctx("market_csgo", "https://market.csgo.com"), client
        )
    assert rows[0].price == Decimal("210.5")
    assert rows[0].volume_24h == 15


def test_aggregate_keeps_cheapest_total_count() -> None:
    from app.services.parsers.base import Listing

    rows = aggregate_listings(
        [
            Listing("A", Decimal("3"), "USD", listings_count=2, count_is_total=True),
            Listing("A", Decimal("2"), "USD", listings_count=5, count_is_total=True),
        ]
    )
    assert rows[0].price == Decimal("2")
    assert rows[0].listings_count == 5
