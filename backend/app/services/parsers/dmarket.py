"""DMarket public market API.

GET https://api.dmarket.com/exchange/v1/market/items
Prices are integer cents. gameId a8db is CS2. Each object is one offer, so
counts are summed per title.
"""

from decimal import Decimal
from typing import Any

import httpx

from app.services.parsers.base import Listing, SiteContext, aggregate_listings, filter_listings
from app.services.parsers.http import get_json

DEFAULT_URL = "https://api.dmarket.com/exchange/v1/market/items"


class DMarketParser:
    slug = "dmarket"

    async def fetch(self, site: SiteContext, client: httpx.AsyncClient) -> list[Listing]:
        return await self._pull(site, client, title=None)

    async def search(
        self, site: SiteContext, client: httpx.AsyncClient, query: str
    ) -> list[Listing]:
        rows = await self._pull(site, client, title=query, max_pages=1)
        return filter_listings(rows, query)

    async def _pull(
        self,
        site: SiteContext,
        client: httpx.AsyncClient,
        *,
        title: str | None,
        max_pages: int | None = None,
    ) -> list[Listing]:
        currency = str(site.config.get("currency") or site.currency or "USD")
        pages = int(max_pages or site.config.get("max_pages") or 3)
        limit = int(site.config.get("page_limit") or 100)
        cursor = ""
        collected: list[Listing] = []
        url = str(site.config.get("items_url") or DEFAULT_URL)
        for _ in range(pages):
            params: dict[str, Any] = {
                "gameId": site.config.get("game_id", "a8db"),
                "currency": currency,
                "limit": limit,
                "orderBy": "title",
                "orderDir": "asc",
            }
            if cursor:
                params["cursor"] = cursor
            if title:
                params["title"] = title
            payload = await get_json(client, url, params=params)
            if not isinstance(payload, dict):
                break
            collected.extend(_offers(payload, currency))
            cursor = str(payload.get("cursor") or "")
            if not cursor:
                break
        return aggregate_listings(collected)


def _offers(payload: dict[str, Any], currency: str) -> list[Listing]:
    objects = payload.get("objects") or payload.get("items") or []
    if not isinstance(objects, list):
        return []
    listings: list[Listing] = []
    for row in objects:
        if not isinstance(row, dict):
            continue
        name = row.get("title") or row.get("name")
        price = _cents(row.get("price"), currency)
        if not name or price is None:
            continue
        raw_extra = row.get("extra")
        extra: dict[str, Any] = raw_extra if isinstance(raw_extra, dict) else {}
        external = row.get("itemId") or extra.get("offerId") or ""
        listings.append(
            Listing(
                raw_name=str(name),
                price=price,
                currency=currency,
                listings_count=1,
                count_is_total=False,
                external_id=str(external) or None,
                metadata={
                    "float": extra.get("floatValue") or extra.get("floatPart"),
                    "phase": extra.get("phase"),
                    "paint_seed": extra.get("paintSeed"),
                },
            )
        )
    return listings


def _cents(price_field: Any, currency: str) -> Decimal | None:
    if isinstance(price_field, dict):
        raw = (
            price_field.get(currency) or price_field.get(currency.upper()) or price_field.get("USD")
        )
    else:
        raw = price_field
    if raw is None or raw == "":
        return None
    return Decimal(str(raw)) / Decimal("100")
