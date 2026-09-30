"""Background poller. Run beside the API, not inside a request."""

import asyncio
import signal

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.session import make_session_factory
from app.services.cache import PriceCache
from app.services.cycle import run_cycle

log = get_logger("worker")


async def main() -> None:
    setup_logging()
    settings = get_settings()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass

    factory = make_session_factory()
    cache = PriceCache(settings.redis_url, settings.price_cache_ttl_seconds)
    log.info(
        "worker_started",
        parser_mode=settings.parser_mode,
        poll_interval_seconds=settings.poll_interval_seconds,
    )
    while not stop.is_set():
        try:
            await run_cycle(factory, cache)
        except Exception as exc:
            log.error("cycle_failed", error=str(exc))
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.poll_interval_seconds)
        except TimeoutError:
            continue
    await cache.close()
    log.info("worker_stopped")


if __name__ == "__main__":
    asyncio.run(main())
