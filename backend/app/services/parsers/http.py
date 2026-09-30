"""HTTP GET with timeouts and retries. This does not evade bot challenges."""

import asyncio
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.parsers.base import ParserError

log = get_logger("http")

USER_AGENT = "CS2TradingBot/1.0 (personal price research; local)"


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    retries: int | None = None,
) -> Any:
    settings = get_settings()
    attempts = retries if retries is not None else settings.http_retries
    delay = 0.5
    last_error: Exception | None = None
    request_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        request_headers.update(headers)

    for attempt in range(1, attempts + 1):
        try:
            response = await client.get(url, params=params, headers=request_headers)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            log.warning("http_transport_error", url=url, attempt=attempt, error=str(exc))
            if attempt == attempts:
                break
            await asyncio.sleep(delay)
            delay *= 2
            continue

        if response.status_code in {429, 500, 502, 503, 504}:
            last_error = ParserError(f"{url} returned {response.status_code}")
            retry_after = response.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
            log.warning(
                "http_retryable_status", url=url, status=response.status_code, attempt=attempt
            )
            if attempt == attempts:
                break
            await asyncio.sleep(min(wait, 30))
            delay *= 2
            continue

        if response.status_code >= 400:
            raise ParserError(f"{url} returned {response.status_code}")

        content_type = response.headers.get("content-type", "")
        body = response.text.lstrip()
        if "html" in content_type or body.startswith("<"):
            raise ParserError(
                f"{url} returned HTML instead of JSON. The official API is not reachable "
                "from this network (often a bot challenge). This client does not bypass it. "
                "Disable the marketplace or use PARSER_MODE=demo."
            )
        try:
            return response.json()
        except ValueError as exc:
            raise ParserError(f"{url} returned invalid JSON") from exc

    raise ParserError(f"Failed to fetch {url}") from last_error
