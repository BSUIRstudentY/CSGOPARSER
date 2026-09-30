"""Request dependencies."""

import os
from collections.abc import AsyncIterator
from decimal import Decimal

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.models import Site, User
from app.schemas.market import SiteOut
from app.services.cache import PriceCache

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token", auto_error=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    factory = request.app.state.session_factory
    async with factory() as session:
        yield session


def get_cache(request: Request) -> PriceCache:
    cache = getattr(request.app.state, "cache", None)
    if cache is None:
        cache = PriceCache("", 0)
        request.app.state.cache = cache
    return cache


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def money(value: Decimal | float | int) -> float:
    return float(value)


def site_out(site: Site) -> SiteOut:
    secret_env = site.secret_env
    return SiteOut(
        id=site.id,
        slug=site.slug,
        name=site.name,
        base_url=site.base_url,
        currency=site.currency,
        buy_fee_pct=money(site.buy_fee_pct),
        sell_fee_pct=money(site.sell_fee_pct),
        deposit_fee_pct=money(site.deposit_fee_pct),
        deposit_fee_flat=money(site.deposit_fee_flat),
        withdraw_fee_pct=money(site.withdraw_fee_pct),
        withdraw_fee_flat=money(site.withdraw_fee_flat),
        trade_lock_days=site.trade_lock_days,
        cash_out=site.cash_out,
        enabled=site.enabled,
        tos_restricted=site.tos_restricted,
        payment_methods=list(site.payment_methods or []),
        config=dict(site.config or {}),
        secret_env=secret_env,
        secret_configured=bool(secret_env and os.environ.get(secret_env)),
        notes=site.notes,
    )
