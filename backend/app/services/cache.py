"""Redis snapshot of the latest price per item and site.

The database remains the source of history. Callers fall back to SQL when Redis
is down or the key is missing.
"""

import json
from typing import Any

from redis.asyncio import Redis

from app.core.logging import get_logger

log = get_logger("cache")


class PriceCache:
    def __init__(self, url: str, ttl_seconds: int) -> None:
        self._url = url.strip()
        self._ttl = ttl_seconds
        self._redis: Redis | None = None

    async def _client(self) -> Redis | None:
        if not self._url:
            return None
        if self._redis is None:
            self._redis = Redis.from_url(self._url, decode_responses=True)
        return self._redis

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def ping(self) -> bool:
        client = await self._client()
        if client is None:
            return False
        try:
            return bool(await client.ping())
        except Exception as exc:
            log.warning("redis_ping_failed", error=str(exc))
            return False

    def _key(self, item_id: int) -> str:
        return f"latest:{item_id}"

    async def get_item(self, item_id: int) -> list[dict[str, Any]] | None:
        client = await self._client()
        if client is None:
            return None
        try:
            raw = await client.hgetall(self._key(item_id))
        except Exception as exc:
            log.warning("redis_read_failed", error=str(exc))
            return None
        if not raw:
            return None
        rows: list[dict[str, Any]] = []
        for payload in raw.values():
            try:
                rows.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
        return rows or None

    async def put_quote(self, item_id: int, site_slug: str, quote: dict[str, Any]) -> None:
        client = await self._client()
        if client is None:
            return
        try:
            key = self._key(item_id)
            await client.hset(key, site_slug, json.dumps(quote))
            await client.expire(key, self._ttl)
        except Exception as exc:
            log.warning("redis_write_failed", error=str(exc))
