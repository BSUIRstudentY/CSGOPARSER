"""FastAPI application."""

import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.db.session import make_engine
from app.services.cache import PriceCache

log = get_logger("api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging()
    settings = get_settings()
    engine = make_engine(settings.database_url)
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    app.state.engine = engine
    app.state.cache = PriceCache(settings.redis_url, settings.price_cache_ttl_seconds)
    app.state.tasks = set()
    log.info("api_started", parser_mode=settings.parser_mode)
    yield
    for task in list(app.state.tasks):
        task.cancel()
    await app.state.cache.close()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CS2 Trading Bot",
        version="1.0.0",
        summary="CS2 skin prices across marketplaces and the spreads between them.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def access_log(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        response = await call_next(request)
        if request.url.path != "/health":
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                ms=round((time.perf_counter() - started) * 1000, 1),
            )
        return response

    @app.get("/health", tags=["health"])
    async def health(request: Request) -> JSONResponse:
        database = False
        try:
            factory = request.app.state.session_factory
            async with factory() as session:
                await session.execute(text("SELECT 1"))
            database = True
        except Exception as exc:
            log.error("health_db_failed", error=str(exc))
        redis_ok = False
        cache = getattr(request.app.state, "cache", None)
        if cache is not None:
            redis_ok = await cache.ping()
        body = {
            "status": "ok" if database else "degraded",
            "database": database,
            "redis": redis_ok,
            "parser_mode": get_settings().parser_mode,
        }
        return JSONResponse(status_code=200 if database else 503, content=body)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(exc, HTTPException):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        log.error("unhandled", path=request.url.path, error=str(exc))
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.include_router(api_router)
    return app


app = create_app()
