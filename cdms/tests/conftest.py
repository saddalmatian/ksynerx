from typing import Any, AsyncIterator

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import Base


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as sess:
        yield sess


def sample_product(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "partnerSKU": "P001",
        "sku": "SKU-001",
        "productName": "Wireless Keyboard",
        "color": "Black",
        "size": "Full",
        "isActive": True,
        "price": 499000,
        "stock": 10,
    }
    base.update(overrides)
    return base
