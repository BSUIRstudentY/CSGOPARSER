"""Canonical catalog, prices, and computed arbitrage routes."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    buy_fee_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=0)
    sell_fee_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=0)
    deposit_fee_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=0)
    deposit_fee_flat: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    withdraw_fee_pct: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=0)
    withdraw_fee_flat: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    trade_lock_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # False when sale proceeds stay inside a closed balance (Steam wallet).
    cash_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tos_restricted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payment_methods: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Non-secret parser options (page caps, min interval). API keys stay in the environment.
    config: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    secret_env: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    aliases: Mapped[list["ItemAlias"]] = relationship(back_populates="site")
    prices: Mapped[list["Price"]] = relationship(back_populates="site")


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        Index("ix_items_weapon_skin_wear", "weapon", "skin_name", "wear"),
        UniqueConstraint("match_key", name="uq_items_match_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    game: Mapped[str] = mapped_column(String(16), nullable=False, default="CS2")
    weapon: Mapped[str] = mapped_column(String(128), nullable=False)
    skin_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    wear: Mapped[str | None] = mapped_column(String(8), nullable=True)
    stattrak: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    souvenir: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    canonical_name: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    match_key: Mapped[str] = mapped_column(String(512), nullable=False)

    aliases: Mapped[list["ItemAlias"]] = relationship(
        back_populates="item",
        foreign_keys="ItemAlias.item_id",
    )
    prices: Mapped[list["Price"]] = relationship(back_populates="item")
    opportunities: Mapped[list["ArbitrageOpportunity"]] = relationship(back_populates="item")


class ItemAlias(Base):
    """Marketplace spelling of a canonical item. Unlinked rows wait for review."""

    __tablename__ = "item_aliases"
    __table_args__ = (UniqueConstraint("site_id", "raw_name", name="uq_alias_site_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    suggested_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True
    )
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    external_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_name: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_key: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    match_method: Mapped[str] = mapped_column(String(32), nullable=False, default="created")
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=1)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    item: Mapped[Item | None] = relationship(
        back_populates="aliases", foreign_keys="ItemAlias.item_id"
    )
    site: Mapped[Site] = relationship(back_populates="aliases")


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (Index("ix_prices_item_site_time", "item_id", "site_id", "captured_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    price_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    listings_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    volume_24h: Mapped[int | None] = mapped_column(Integer, nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Column name stays "metadata"; the attribute is "details" because DeclarativeBase
    # already uses the name metadata.
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)

    item: Mapped[Item] = relationship(back_populates="prices")
    site: Mapped[Site] = relationship(back_populates="prices")


class ArbitrageOpportunity(Base):
    __tablename__ = "arbitrage_opportunities"
    __table_args__ = (
        UniqueConstraint("item_id", "buy_site_id", "sell_site_id", name="uq_arb_route"),
        Index("ix_arbitrage_active_profit", "is_active", "profit_pct"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    buy_site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    sell_site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"))
    buy_price_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    sell_price_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    proceeds_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    profit_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    profit_pct: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    liquidity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    instant_trade: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trade_lock_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cash_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    item: Mapped[Item] = relationship(back_populates="opportunities")
    buy_site: Mapped[Site] = relationship(foreign_keys=[buy_site_id])
    sell_site: Mapped[Site] = relationship(foreign_keys=[sell_site_id])


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    settings: Mapped["UserSettings | None"] = relationship(back_populates="user")
    saved_searches: Mapped[list["SavedSearch"]] = relationship(back_populates="user")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="user")


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    default_filters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="settings")


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="saved_searches")


class Alert(Base):
    """Stored alert definition. Delivery to Telegram or Discord is intentionally not implemented."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="telegram")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="alerts")


class ParserRun(Base):
    __tablename__ = "parser_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    site_id: Mapped[int] = mapped_column(ForeignKey("sites.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    items_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_upserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    site: Mapped[Site] = relationship()


class FxRate(Base):
    __tablename__ = "fx_rates"

    currency: Mapped[str] = mapped_column(String(8), primary_key=True)
    usd_per_unit: Mapped[Decimal] = mapped_column(Numeric(16, 8), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
