"""API router."""

from fastapi import APIRouter

from app.api.routes import admin, arbitrage, auth, items, market, sites, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(items.router)
api_router.include_router(market.router)
api_router.include_router(arbitrage.router)
api_router.include_router(sites.router)
api_router.include_router(users.router)
api_router.include_router(admin.router)
