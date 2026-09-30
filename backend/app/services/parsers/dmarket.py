"""DMarket marketplace offers.

GET https://api.dmarket.com/marketplace-api/v2/offers
The previous /exchange/v1/market/items route is retired. v2 requires an Ed25519
signed request (X-Api-Key, X-Sign-Date, X-Request-Sign). Prices are integer
cents. gameId a8db is CS2. Each item is one offer, so counts are summed per title.
"""

import os
import time
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx
from nacl.signing import SigningKey

from app.services.parsers.base import (
    Listing,
    ParserError,
    SiteContext,
    aggregate_listings,
    filter_listings,
)
from app.services.parsers.http import get_json

OFFERS_PATH = "/marketplace-api/v2/offers"
# Wider than the first 3-page sample. Steam stays on its own smaller cap.
DEFAULT_MAX_PAGES = 25


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
        public_key, signing_key = _keys()
        currency = str(site.config.get("currency") or site.currency or "USD")
        pages = int(max_pages or site.config.get("max_pages") or DEFAULT_MAX_PAGES)
        limit = min(int(site.config.get("page_limit") or 100), 100)
        cursor = ""
        collected: list[Listing] = []
        origin = str(site.base_url or "https://api.dmarket.com").rstrip("/")
        for _ in range(pages):
            pairs: list[tuple[str, str]] = [
                ("gameId", str(site.config.get("game_id") or "a8db")),
                ("limit", str(limit)),
                ("orderBy", "title"),
                ("orderDir", "asc"),
            ]
            if title:
                pairs.append(("title", title))
            if cursor:
                pairs.append(("cursor", cursor))
            query = _query(pairs)
            signed_path = f"{OFFERS_PATH}?{query}"
            payload = await get_json(
                client,
                f"{origin}{signed_path}",
                headers=_sign_headers(public_key, signing_key, signed_path),
            )
            if not isinstance(payload, dict):
                break
            collected.extend(_offers(payload, currency))
            cursor = str(payload.get("cursor") or "")
            if not cursor:
                break
        return aggregate_listings(collected)


def _query(pairs: list[tuple[str, str]]) -> str:
    return "&".join(f"{quote(key, safe='')}={quote(value, safe='')}" for key, value in pairs)


def _keys() -> tuple[str, SigningKey]:
    public_key = os.environ.get("DMARKET_PUBLIC_KEY", "").strip().lower()
    secret = os.environ.get("DMARKET_SECRET_KEY", "").strip()
    if not public_key or not secret:
        raise ParserError(
            "DMarket /marketplace-api/v2/offers requires DMARKET_PUBLIC_KEY and "
            "DMARKET_SECRET_KEY. /exchange/v1/market/items is retired and unsigned "
            "requests are rejected. This client does not use a website scrape instead."
        )
    try:
        raw = bytes.fromhex(secret)
    except ValueError as exc:
        raise ParserError("DMARKET_SECRET_KEY must be hex") from exc
    if len(raw) == 64:
        raw = raw[:32]
    if len(raw) != 32:
        raise ParserError("DMARKET_SECRET_KEY must be a 32-byte or 64-byte hex Ed25519 key")
    return public_key, SigningKey(raw)


def _sign_headers(public_key: str, signing_key: SigningKey, signed_path: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    # Method + path and query + empty body + timestamp. Query stays percent-encoded.
    message = f"GET{signed_path}{timestamp}".encode()
    signature = signing_key.sign(message).signature.hex()
    return {
        "X-Api-Key": public_key,
        "X-Sign-Date": timestamp,
        "X-Request-Sign": f"dmar ed25519 {signature}",
    }


def _offers(payload: dict[str, Any], currency: str) -> list[Listing]:
    objects = payload.get("items") or payload.get("objects") or []
    if not isinstance(objects, list):
        return []
    listings: list[Listing] = []
    for row in objects:
        if not isinstance(row, dict):
            continue
        attributes = row.get("attributes")
        attrs: dict[str, Any] = attributes if isinstance(attributes, dict) else {}
        cs2 = attrs.get("cs2Attributes")
        extra: dict[str, Any] = cs2 if isinstance(cs2, dict) else attrs
        name = attrs.get("title") or row.get("title") or row.get("name")
        price = _cents(row.get("priceCents", row.get("price")), currency)
        if not name or price is None:
            continue
        listings.append(
            Listing(
                raw_name=str(name),
                price=price,
                currency=currency,
                listings_count=1,
                count_is_total=False,
                external_id=str(row.get("offerId") or "") or None,
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
