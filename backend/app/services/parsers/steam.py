"""Steam Community Market search JSON.

This is the same render endpoint the market website uses, not a documented
partner API. Keep max_pages low. sell_price is the buyer-facing price in cents
when currency=1 (USD). Selling on Steam pays the Steam wallet, not cash.
"""

import asyncio
from decimal import Decimal
from typing import Any

import httpx

from app.services.parsers.base import Listing, SiteContext, aggregate_listings
from app.services.parsers.http import get_json


class SteamParser:
    slug = "steam"

    async def fetch(self, site: SiteContext, client: httpx.AsyncClient) -> list[Listing]:
        return await self._pages(site, client, query="")

    async def search(
        self, site: SiteContext, client: httpx.AsyncClient, query: str
    ) -> list[Listing]:
        return await self._pages(site, client, query=query, max_pages=1)

    async def _pages(
        self,
        site: SiteContext,
        client: httpx.AsyncClient,
        *,
        query: str,
        max_pages: int | None = None,
    ) -> list[Listing]:
        pages = int(max_pages or site.config.get("max_pages") or 2)
        count = int(site.config.get("page_size") or 100)
        delay = float(site.config.get("page_delay_seconds") or 1.5)
        listings: list[Listing] = []
        for page in range(pages):
            params = {
                "query": query,
                "start": page * count,
                "count": count,
                "search_descriptions": 0,
                "sort_column": "popular",
                "sort_dir": "desc",
                "appid": 730,
                "norender": 1,
                "currency": 1,
            }
            payload = await get_json(
                client,
                f"{site.base_url.rstrip('/')}/market/search/render/",
                params=params,
            )
            listings.extend(_results(payload))
            if page < pages - 1:
                await asyncio.sleep(delay)
        return aggregate_listings(listings)


def _results(payload: Any) -> list[Listing]:
    if not isinstance(payload, dict) or not payload.get("success", True):
        return []
    rows = payload.get("results") or []
    if not isinstance(rows, list):
        return []
    listings: list[Listing] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("hash_name") or row.get("name")
        sell_price = row.get("sell_price")
        if not name or sell_price is None:
            continue
        listings_count = row.get("sell_listings")
        listings.append(
            Listing(
                raw_name=str(name),
                price=Decimal(str(sell_price)) / Decimal("100"),
                currency="USD",
                listings_count=int(listings_count) if listings_count is not None else None,
            )
        )
    return listings
