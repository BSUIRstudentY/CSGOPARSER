"""market.csgo.com public price file.

GET https://market.csgo.com/api/v2/prices/USD.json
Official price export used by their own API docs. Prices are USD strings.
"""

from decimal import Decimal
from typing import Any

import httpx

from app.services.parsers.base import Listing, SiteContext, aggregate_listings, filter_listings
from app.services.parsers.http import get_json


class MarketCsgoParser:
    slug = "market_csgo"
    _cache: list[Listing] | None = None

    async def fetch(self, site: SiteContext, client: httpx.AsyncClient) -> list[Listing]:
        url = f"{site.base_url.rstrip('/')}/api/v2/prices/USD.json"
        payload = await get_json(client, url)
        listings = _parse(payload)
        self._cache = listings
        return listings

    async def search(
        self, site: SiteContext, client: httpx.AsyncClient, query: str
    ) -> list[Listing]:
        if self._cache is None:
            await self.fetch(site, client)
        return filter_listings(self._cache or [], query)


def _parse(payload: Any) -> list[Listing]:
    items: Any
    if isinstance(payload, dict):
        if payload.get("success") is False:
            return []
        items = payload.get("items")
    else:
        items = payload
    rows: list[dict[str, Any]] = []
    if isinstance(items, list):
        rows = [row for row in items if isinstance(row, dict)]
    elif isinstance(items, dict):
        for name, value in items.items():
            if isinstance(value, dict):
                rows.append({"market_hash_name": name, **value})
            else:
                rows.append({"market_hash_name": name, "price": value})
    listings: list[Listing] = []
    for row in rows:
        name = row.get("market_hash_name") or row.get("name")
        raw_price = row.get("price")
        if not name or raw_price is None:
            continue
        volume = row.get("volume")
        volume_text = str(volume).strip() if volume not in (None, "") else ""
        count = int(volume_text) if volume_text.isdigit() else None
        listings.append(
            Listing(
                raw_name=str(name),
                price=Decimal(str(raw_price)),
                currency=str(row.get("currency") or "USD"),
                volume_24h=count,
                listings_count=count,
            )
        )
    return aggregate_listings(listings)
