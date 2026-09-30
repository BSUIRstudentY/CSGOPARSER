"""Waxpeer public price list.

GET https://api.waxpeer.com/v1/prices?game=csgo
`min` is in thousandths of a US dollar (1000 = $1). No key is required for this route.
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
        url = f"{site.base_url.rstrip('/')}/v1/prices"
        payload = await get_json(client, url, params={"game": site.config.get("game", "csgo")})
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
    return aggregate_listings(listings)
