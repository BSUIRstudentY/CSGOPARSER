"""Runtime configuration. Marketplace fees live in the database, not here."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://csgobot:csgobot@localhost:5432/csgobot"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-change-me"
    jwt_expire_minutes: int = 60 * 24
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    # demo: synthetic prices so the stack runs offline. live: call marketplace APIs.
    parser_mode: str = "demo"
    poll_interval_seconds: int = 300
    http_timeout_seconds: float = 30.0
    http_retries: int = 3
    # Opportunities below this profit percent are not stored. 0 keeps only non-negative rows.
    arb_min_store_pct: float = 0.0
    fuzzy_auto_threshold: float = 97.0
    fuzzy_review_threshold: float = 90.0
    fuzzy_budget_per_cycle: int = 200
    seed_demo_user: bool = True
    allow_registration: bool = True
    admin_email: str = "admin@localhost"
    admin_password: str = "changeme"
    log_level: str = "INFO"
    price_cache_ttl_seconds: int = 3600

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
