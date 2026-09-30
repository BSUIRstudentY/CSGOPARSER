"""Waxpeer public prices and buy orders.

GET https://api.waxpeer.com/v1/prices?game=csgo
`min` is the cheapest listing, in thousandths of a US dollar (1000 = $1).

GET https://api.waxpeer.com/v1/buy-orders/snapshot?game=csgo
`max` is the highest buy order for that name, in the same thousandths. No key.
The market comparison uses this demand price, not `min`.
"""

from decimal import Decimal
from typing import Any

import httpx

from app.services.parsers.base import Listing, SiteContext, aggregate_listings, filter_listings
from app.services.parsers.http import get_json


class WaxpeerParser:
    slug = "waxpeer"
    _cache: list[Listing] | None = None

    async def fetch(self, site: SiteContext, client: httpx.AsyncClient) -> list[Listing]:
        game = site.config.get("game", "csgo")
        origin = site.base_url.rstrip("/")
        prices = await get_json(client, f"{origin}/v1/prices", params={"game": game})
        orders = await get_json(client, f"{origin}/v1/buy-orders/snapshot", params={"game": game})
        listings = _parse(prices, orders)
        self._cache = listings
        return listings

    async def search(
        self, site: SiteContext, client: httpx.AsyncClient, query: str
    ) -> list[Listing]:
        if self._cache is None:
            await self.fetch(site, client)
        return filter_listings(self._cache or [], query)


def _parse(prices: Any, orders: Any) -> list[Listing]:
    listings = aggregate_listings(_asks(prices))
    bids = _bids(orders)
    for row in listings:
        bid = bids.get(row.raw_name)
        if bid is not None and bid > 0:
            row.bid = bid
    return listings


def _asks(payload: Any) -> list[Listing]:
    items: list[Any]
    if isinstance(payload, dict):
        raw_items = payload.get("items") or []
        items = raw_items if isinstance(raw_items, list) else []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []
    listings: list[Listing] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        name = row.get("name") or row.get("market_hash_name")
        raw_min = row.get("min")
        if not name or raw_min is None:
            continue
        price = Decimal(str(raw_min)) / Decimal("1000")
        count = row.get("count")
        listings.append(
            Listing(
                raw_name=str(name),
                price=price,
                currency="USD",
                listings_count=int(count) if count is not None else None,
            )
        )
    return listings


def _bids(payload: Any) -> dict[str, Decimal]:
    offers: list[Any]
    if isinstance(payload, dict):
        raw = payload.get("offers") or []
        offers = raw if isinstance(raw, list) else []
    elif isinstance(payload, list):
        offers = payload
    else:
        offers = []
    bids: dict[str, Decimal] = {}
    for row in offers:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        raw_max = row.get("max")
        if not name or raw_max is None:
            continue
        key = " ".join(str(name).split())
        price = Decimal(str(raw_max)) / Decimal("1000")
        if price <= 0:
            continue
        current = bids.get(key)
        if current is None or price > current:
            bids[key] = price
    return bids
