"""market.csgo.com public class/instance price file, including buy orders.

GET https://market.csgo.com/api/v2/prices/class_instance/USD.json
`price` is an ask for that class instance. `buy_order` is its maximum buy order.
Many instances share one market hash name (float, stickers). The demand quote is
the highest buy order that does not exceed the cheapest ask for that name.
A higher buy order on an expensive instance is not the bid for the liquid item.
"""

from decimal import Decimal
from typing import Any

import httpx

from app.services.parsers.base import (
    Listing,
    ParserError,
    SiteContext,
    aggregate_listings,
    filter_listings,
)
from app.services.parsers.http import USER_AGENT

CLASS_INSTANCE_PATH = "/api/v2/prices/class_instance/USD.json"


class MarketCsgoParser:
    slug = "market_csgo"
    _cache: list[Listing] | None = None

    async def fetch(self, site: SiteContext, client: httpx.AsyncClient) -> list[Listing]:
        url = f"{site.base_url.rstrip('/')}{CLASS_INSTANCE_PATH}"
        payload = await _get_json(client, url)
        listings = _parse(payload)
        self._cache = listings
        return listings

    async def search(
        self, site: SiteContext, client: httpx.AsyncClient, query: str
    ) -> list[Listing]:
        if self._cache is None:
            await self.fetch(site, client)
        return filter_listings(self._cache or [], query)


async def _get_json(client: httpx.AsyncClient, url: str) -> Any:
    """Download the class/instance file without copying the body into a second string."""
    try:
        response = await client.get(
            url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
        )
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise ParserError(f"Failed to fetch {url}") from exc
    if response.status_code >= 400:
        raise ParserError(f"{url} returned {response.status_code}")
    content_type = response.headers.get("content-type", "")
    if "html" in content_type or response.content.lstrip()[:1] == b"<":
        raise ParserError(
            f"{url} returned HTML instead of JSON. The official API is not reachable "
            "from this network (often a bot challenge). This client does not bypass it. "
            "Disable the marketplace or use PARSER_MODE=demo."
        )
    try:
        return response.json()
    except ValueError as exc:
        raise ParserError(f"{url} returned invalid JSON") from exc


def _parse(payload: Any) -> list[Listing]:
    if isinstance(payload, dict) and payload.get("success") is False:
        return []
    items: Any = payload.get("items") if isinstance(payload, dict) else payload
    if isinstance(items, dict) and _is_class_instance(items):
        return _from_class_instances(items)
    return _from_best_offers(items)


def _is_class_instance(items: dict[Any, Any]) -> bool:
    for value in items.values():
        return isinstance(value, dict) and ("buy_order" in value or "market_hash_name" in value)
    return False


def _from_class_instances(items: dict[Any, Any]) -> list[Listing]:
    grouped: dict[str, list[tuple[Decimal, Decimal]]] = {}
    for value in items.values():
        if not isinstance(value, dict):
            continue
        name = value.get("market_hash_name") or value.get("name")
        raw_price = value.get("price")
        if not name or raw_price in (None, ""):
            continue
        ask = _decimal(raw_price)
        if ask is None or ask <= 0:
            continue
        bid = _decimal(value.get("buy_order")) or Decimal("0")
        key = " ".join(str(name).split())
        grouped.setdefault(key, []).append((ask, bid))
    listings: list[Listing] = []
    for name, pairs in grouped.items():
        min_ask = min(ask for ask, _bid in pairs)
        eligible = [bid for _ask, bid in pairs if bid > 0 and bid <= min_ask]
        best_bid = max(eligible) if eligible else None
        listings.append(
            Listing(
                raw_name=name,
                price=min_ask,
                currency="USD",
                bid=best_bid,
            )
        )
    return listings


def _from_best_offers(items: Any) -> list[Listing]:
    """Older one-row-per-name export. It has asks only, so bids stay empty."""
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
        parsed_bid = _decimal(row.get("buy_order"))
        bid = parsed_bid if parsed_bid is not None and parsed_bid > 0 else None
        listings.append(
            Listing(
                raw_name=str(name),
                price=Decimal(str(raw_price)),
                currency=str(row.get("currency") or "USD"),
                volume_24h=count,
                listings_count=count,
                bid=bid,
            )
        )
    return aggregate_listings(listings)


def _decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None
