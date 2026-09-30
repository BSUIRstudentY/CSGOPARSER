"""Marketplace, item, and arbitrage payloads."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SiteOut(BaseModel):
    id: int
    slug: str
    name: str
    base_url: str
    currency: str
    buy_fee_pct: float
    sell_fee_pct: float
    deposit_fee_pct: float
    deposit_fee_flat: float
    withdraw_fee_pct: float
    withdraw_fee_flat: float
    trade_lock_days: int
    cash_out: bool
    enabled: bool
    tos_restricted: bool
    payment_methods: list[str]
    config: dict[str, Any]
    secret_env: str | None
    secret_configured: bool
    notes: str | None


class SiteUpdate(BaseModel):
    base_url: str | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=8)
    buy_fee_pct: float | None = Field(default=None, ge=0, le=0.5)
    sell_fee_pct: float | None = Field(default=None, ge=0, le=0.5)
    deposit_fee_pct: float | None = Field(default=None, ge=0, le=0.5)
    deposit_fee_flat: float | None = Field(default=None, ge=0, le=10000)
    withdraw_fee_pct: float | None = Field(default=None, ge=0, le=0.5)
    withdraw_fee_flat: float | None = Field(default=None, ge=0, le=10000)
    trade_lock_days: int | None = Field(default=None, ge=0, le=30)
    cash_out: bool | None = None
    enabled: bool | None = None
    notes: str | None = None
    config: dict[str, Any] | None = None


class ItemOut(BaseModel):
    id: int
    game: str
    weapon: str
    skin_name: str
    wear: str | None
    stattrak: bool
    souvenir: bool
    canonical_name: str


class PricePointOut(BaseModel):
    site: str
    price: float
    price_usd: float
    currency: str
    listings_count: int | None
    volume_24h: int | None
    captured_at: datetime
    # Highest buy order. Empty on older ask-only rows.
    bid_usd: float | None = None


class ListingSearchOut(BaseModel):
    raw_name: str
    price: float
    currency: str
    listings_count: int | None


class QuoteOut(BaseModel):
    site: str
    site_name: str
    price_usd: float
    listings_count: int | None
    url: str


class MarketCardOut(BaseModel):
    item_id: int
    canonical_name: str
    weapon: str
    skin_name: str
    wear: str | None
    stattrak: bool
    souvenir: bool
    cheapest: QuoteOut
    highest: QuoteOut
    spread_usd: float
    spread_pct: float
    quotes: list[QuoteOut]


class OpportunityOut(BaseModel):
    id: int
    item_id: int
    canonical_name: str
    weapon: str
    skin_name: str
    wear: str | None
    stattrak: bool
    souvenir: bool
    buy_site: str
    sell_site: str
    buy_price_usd: float
    sell_price_usd: float
    cost_usd: float
    proceeds_usd: float
    profit_usd: float
    profit_pct: float
    liquidity: int
    instant_trade: bool
    trade_lock_days: int
    cash_out: bool
    computed_at: datetime


class ParserRunOut(BaseModel):
    id: int
    site: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    items_fetched: int
    items_upserted: int
    error: str | None


class StatsOut(BaseModel):
    items: int
    opportunities: int
    best_profit_usd: float | None
    best_profit_pct: float | None
    parser_mode: str
    sites_enabled: int
    last_runs: list[ParserRunOut]


class AliasOut(BaseModel):
    id: int
    site: str
    raw_name: str
    normalized_key: str
    match_method: str
    confidence: float
    needs_review: bool
    item_id: int | None
    suggested_item_id: int | None


class AliasLink(BaseModel):
    item_id: int


class FiltersPayload(BaseModel):
    q: str | None = None
    weapon: str | None = None
    wear: str | None = None
    stattrak: bool | None = None
    souvenir: bool | None = None
    min_profit: float | None = None
    min_profit_pct: float | None = None
    min_liquidity: int | None = None
    buy_site: list[str] = Field(default_factory=list)
    sell_site: list[str] = Field(default_factory=list)
    exclude_site: list[str] = Field(default_factory=list)
    instant_only: bool = False
    cash_out_only: bool = False


class SettingsOut(BaseModel):
    default_filters: FiltersPayload


class SettingsUpdate(BaseModel):
    default_filters: FiltersPayload


class SavedSearchIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    filters: FiltersPayload


class SavedSearchOut(BaseModel):
    id: int
    name: str
    filters: FiltersPayload
    created_at: datetime | None = None


class AlertIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    filters: FiltersPayload
    channel: str = Field(pattern="^(telegram|discord|email)$")
    enabled: bool = True


class AlertUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    filters: FiltersPayload | None = None
    channel: str | None = Field(default=None, pattern="^(telegram|discord|email)$")
    enabled: bool | None = None


class AlertOut(BaseModel):
    id: int
    name: str
    filters: FiltersPayload
    channel: str
    enabled: bool
    created_at: datetime | None = None
    delivery: str = "stored_only"
