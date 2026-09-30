"""Shared listing shape for every marketplace client."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol

import httpx


class ParserError(Exception):
    """A marketplace request failed or returned a payload we refuse to treat as prices."""


@dataclass
class Listing:
    raw_name: str
    price: Decimal
    currency: str
    listings_count: int | None = None
    volume_24h: int | None = None
    external_id: str | None = None
    # True when listings_count is already the market total. False when each row is one offer.
    count_is_total: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SiteContext:
    slug: str
    base_url: str
    currency: str
    config: dict[str, Any]


class MarketplaceParser(Protocol):
    slug: str

    async def fetch(self, site: SiteContext, client: httpx.AsyncClient) -> list[Listing]: ...

    async def search(
        self, site: SiteContext, client: httpx.AsyncClient, query: str
    ) -> list[Listing]: ...


def aggregate_listings(listings: list[Listing]) -> list[Listing]:
    """Collapse duplicate names to the cheapest ask and a single listing count."""
    grouped: dict[str, Listing] = {}
    counts: dict[str, int] = {}
    totals: dict[str, bool] = {}
    for row in listings:
        name = " ".join(row.raw_name.split())
        if not name or row.price <= 0:
            continue
        piece = row.listings_count if row.listings_count is not None else 1
        if name not in counts:
            counts[name] = piece
            totals[name] = row.count_is_total
        elif row.count_is_total and totals[name]:
            counts[name] = max(counts[name], piece)
        else:
            counts[name] = counts[name] + piece
            totals[name] = False
        current = grouped.get(name)
        if current is None or row.price < current.price:
            grouped[name] = Listing(
                raw_name=name,
                price=row.price,
                currency=row.currency.upper(),
                listings_count=piece,
                volume_24h=row.volume_24h,
                external_id=row.external_id,
                count_is_total=True,
                metadata=dict(row.metadata),
            )
    result: list[Listing] = []
    for name, row in grouped.items():
        row.listings_count = counts[name]
        result.append(row)
    return result


def filter_listings(listings: list[Listing], query: str) -> list[Listing]:
    needle = query.strip().lower()
    if not needle:
        return []
    return [row for row in listings if needle in row.raw_name.lower()]
