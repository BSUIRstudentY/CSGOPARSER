"""Initial catalog, prices, and arbitrage tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("base_url", sa.String(255), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("buy_fee_pct", sa.Numeric(8, 6), nullable=False),
        sa.Column("sell_fee_pct", sa.Numeric(8, 6), nullable=False),
        sa.Column("deposit_fee_pct", sa.Numeric(8, 6), nullable=False),
        sa.Column("deposit_fee_flat", sa.Numeric(14, 4), nullable=False),
        sa.Column("withdraw_fee_pct", sa.Numeric(8, 6), nullable=False),
        sa.Column("withdraw_fee_flat", sa.Numeric(14, 4), nullable=False),
        sa.Column("trade_lock_days", sa.Integer(), nullable=False),
        sa.Column("cash_out", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("tos_restricted", sa.Boolean(), nullable=False),
        sa.Column("payment_methods", sa.JSON(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("secret_env", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game", sa.String(16), nullable=False),
        sa.Column("weapon", sa.String(128), nullable=False),
        sa.Column("skin_name", sa.String(255), nullable=False),
        sa.Column("wear", sa.String(8), nullable=True),
        sa.Column("stattrak", sa.Boolean(), nullable=False),
        sa.Column("souvenir", sa.Boolean(), nullable=False),
        sa.Column("canonical_name", sa.String(512), nullable=False, unique=True),
        sa.Column("match_key", sa.String(512), nullable=False),
        sa.UniqueConstraint("match_key", name="uq_items_match_key"),
    )
    op.create_index("ix_items_weapon_skin_wear", "items", ["weapon", "skin_name", "wear"])
    op.create_table(
        "item_aliases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE")),
        sa.Column(
            "suggested_item_id",
            sa.Integer(),
            sa.ForeignKey("items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("external_id", sa.String(128), nullable=True),
        sa.Column("raw_name", sa.String(512), nullable=False),
        sa.Column("normalized_key", sa.String(512), nullable=False),
        sa.Column("match_method", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Numeric(6, 4), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("site_id", "raw_name", name="uq_alias_site_name"),
    )
    op.create_table(
        "prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("price", sa.Numeric(14, 4), nullable=False),
        sa.Column("price_usd", sa.Numeric(14, 4), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("listings_count", sa.Integer(), nullable=True),
        sa.Column("volume_24h", sa.Integer(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
    )
    op.create_index("ix_prices_item_id", "prices", ["item_id"])
    op.create_index("ix_prices_site_id", "prices", ["site_id"])
    op.create_index("ix_prices_item_site_time", "prices", ["item_id", "site_id", "captured_at"])
    op.create_table(
        "arbitrage_opportunities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "item_id", sa.Integer(), sa.ForeignKey("items.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "buy_site_id",
            sa.Integer(),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sell_site_id",
            sa.Integer(),
            sa.ForeignKey("sites.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("buy_price_usd", sa.Numeric(14, 4), nullable=False),
        sa.Column("sell_price_usd", sa.Numeric(14, 4), nullable=False),
        sa.Column("cost_usd", sa.Numeric(14, 4), nullable=False),
        sa.Column("proceeds_usd", sa.Numeric(14, 4), nullable=False),
        sa.Column("profit_usd", sa.Numeric(14, 4), nullable=False),
        sa.Column("profit_pct", sa.Numeric(10, 4), nullable=False),
        sa.Column("liquidity", sa.Integer(), nullable=False),
        sa.Column("instant_trade", sa.Boolean(), nullable=False),
        sa.Column("trade_lock_days", sa.Integer(), nullable=False),
        sa.Column("cash_out", sa.Boolean(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("item_id", "buy_site_id", "sell_site_id", name="uq_arb_route"),
    )
    op.create_index(
        "ix_arbitrage_active_profit", "arbitrage_opportunities", ["is_active", "profit_pct"]
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "user_settings",
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("default_filters", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "saved_searches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_saved_searches_user_id", "saved_searches", ["user_id"])
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("filters", sa.JSON(), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_alerts_user_id", "alerts", ["user_id"])
    op.create_table(
        "parser_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "site_id", sa.Integer(), sa.ForeignKey("sites.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("items_fetched", sa.Integer(), nullable=False),
        sa.Column("items_upserted", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_parser_runs_site_id", "parser_runs", ["site_id"])
    op.create_table(
        "fx_rates",
        sa.Column("currency", sa.String(8), primary_key=True),
        sa.Column("usd_per_unit", sa.Numeric(16, 8), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    for name in (
        "fx_rates",
        "parser_runs",
        "alerts",
        "saved_searches",
        "user_settings",
        "users",
        "arbitrage_opportunities",
        "prices",
        "item_aliases",
        "items",
        "sites",
    ):
        op.drop_table(name)
