# ruff: noqa: E402
import os
from collections.abc import AsyncIterator
from pathlib import Path

# Environment must be set before the app reads settings.
_DB = Path(__file__).resolve().parent / ".pytest.db"
if _DB.exists():
    _DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB}"
os.environ["REDIS_URL"] = ""
os.environ["JWT_SECRET"] = "test-secret-key-with-32-bytes-min"
os.environ["PARSER_MODE"] = "demo"
os.environ["SEED_DEMO_USER"] = "false"
os.environ["ALLOW_REGISTRATION"] = "true"
os.environ["ARB_MIN_STORE_PCT"] = "0"

from app.core.config import get_settings

get_settings.cache_clear()

import pytest
from app.db.base import Base
from app.db.models import User
from app.main import app
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        factory = app.state.session_factory
        async with factory() as session:
            conn = await session.connection()
            await conn.run_sync(Base.metadata.create_all)
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(delete(table))
            await session.commit()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http


@pytest.fixture
async def db_session(client: AsyncClient) -> AsyncIterator[AsyncSession]:
    factory = app.state.session_factory
    async with factory() as session:
        yield session


async def auth_header(client: AsyncClient, email: str = "trader@localhost") -> dict[str, str]:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": "supersecret"},
    )
    if response.status_code == 409:
        response = await client.post(
            "/auth/login",
            json={"email": email, "password": "supersecret"},
        )
    assert response.status_code in {200, 201}, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def promote(session: AsyncSession, email: str) -> None:
    from sqlalchemy import select

    user = (await session.execute(select(User).where(User.email == email))).scalar_one()
    user.is_admin = True
    await session.commit()
