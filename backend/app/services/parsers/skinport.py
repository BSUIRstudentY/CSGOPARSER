"""Skinport official public API: GET https://api.skinport.com/v1/items.

No API key. Rate limit is 8 requests / 5 minutes and Brotli is required.
Cloudflare may still challenge server-side clients; that failure is reported,
not bypassed.
"""

from decimal import Decimal
from typing import Any

import httpx

from app.services.parsers.base import Listing, SiteContext, aggregate_listings, filter_listings
from app.services.parsers.http import get_json


class SkinportParser:
    slug = "skinport"

    async def fetch(self, site: SiteContext, client: httpx.AsyncClient) -> list[Listing]:
        currency = str(site.config.get("currency") or site.currency or "USD")
        tradable = site.config.get("tradable", True)
        payload = await get_json(
            client,
            f"{site.base_url.rstrip('/')}/v1/items",
            params={"app_id": 730, "currency": currency, "tradable": int(bool(tradable))},
            headers={"Accept-Encoding": "br"},
        )
        return _parse_items(payload, currency)

    async def search(
        self, site: SiteContext, client: httpx.AsyncClient, query: str
    ) -> list[Listing]:
        # The items endpoint has no name filter. Search reuses the cached catalog response.
        return filter_listings(await self.fetch(site, client), query)


def _parse_items(payload: Any, currency: str) -> list[Listing]:
    if not isinstance(payload, list):
        return []
    listings: list[Listing] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        name = row.get("market_hash_name")
        raw_price = row.get("min_price")
        if raw_price is None:
            raw_price = row.get("suggested_price")
        if not name or raw_price is None:
            continue
        price = Decimal(str(raw_price))
        quantity = row.get("quantity")
        listings.append(
            Listing(
                raw_name=str(name),
                price=price,
                currency=str(row.get("currency") or currency),
                listings_count=int(quantity) if quantity is not None else None,
                metadata={
                    "suggested_price": row.get("suggested_price"),
                    "mean_price": row.get("mean_price"),
                    "item_page": row.get("item_page"),
                },
            )
        )
    return aggregate_listings(listings)
