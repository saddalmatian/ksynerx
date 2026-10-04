"""Phase 6 — exactly-once under concurrent writes."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.database import Base
from app.models.product_change import ProductChange
from app.services.change_processor import process_product


def _product(tag: str, **overrides: Any) -> dict[str, Any]:
    base = {
        "partnerSKU": tag,
        "sku": f"SKU-{tag}",
        "productName": f"Product {tag}",
        "stock": 10,
        "price": 1000,
        "isActive": True,
    }
    base.update(overrides)
    return base


@pytest_asyncio.fixture
async def file_engine(tmp_path) -> AsyncIterator:
    url = f"sqlite+aiosqlite:///{tmp_path}/concurrency.db"
    eng = create_async_engine(url, connect_args={"timeout": 30}, future=True)
    async with eng.begin() as conn:
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def maker(file_engine):
    return async_sessionmaker(file_engine, class_=AsyncSession, expire_on_commit=False)


async def _process(maker, product: dict[str, Any], source: str) -> bool:
    async with maker() as session:
        result = await process_product(session, product, source=source)
        return result.stored


async def _count_changes(maker) -> int:
    async with maker() as session:
        row = await session.execute(select(func.count()).select_from(ProductChange))
        return int(row.scalar_one())


async def test_concurrent_identical_payloads_store_once(maker):
    """N concurrent writers, same payload -> exactly 1 stored change."""
    n = 20
    payload = _product("SAME")
    stored_flags = await asyncio.gather(
        *[_process(maker, payload, "webhook") for _ in range(n)]
    )
    assert sum(1 for s in stored_flags if s) == 1
    assert await _count_changes(maker) == 1


async def test_concurrent_distinct_payloads_all_store(maker):
    """N concurrent writers, distinct payloads -> all stored."""
    n = 30
    products = [_product(f"P{i:03d}") for i in range(n)]
    stored_flags = await asyncio.gather(
        *[_process(maker, p, "webhook") for p in products]
    )
    assert all(stored_flags)
    assert await _count_changes(maker) == n


async def test_concurrent_mixed_mechanisms_same_payload(maker):
    """webhook + polling + excel race on identical payload -> 1 row."""
    payload = _product("RACE")
    sources = ["webhook", "polling", "excel"] * 10
    stored_flags = await asyncio.gather(
        *[_process(maker, payload, src) for src in sources]
    )
    assert sum(1 for s in stored_flags if s) == 1
    assert await _count_changes(maker) == 1


async def test_concurrent_burst_with_later_change(maker):
    """Burst of identical writes, then one real change -> 2 rows total."""
    payload = _product("BURST", stock=10)
    await asyncio.gather(*[_process(maker, payload, "webhook") for _ in range(50)])
    changed = _product("BURST", stock=99)
    stored_flags = await asyncio.gather(
        *[_process(maker, changed, "polling") for _ in range(50)]
    )
    assert sum(1 for s in stored_flags if s) == 1
    assert await _count_changes(maker) == 2


async def test_concurrent_replay_across_sources_same_data_hash(maker):
    """Same logical data arriving via different sources shares one hash."""
    payload = _product("SAMEHASH", stock=42)
    sources = ["webhook", "excel", "polling", "webhook", "excel", "polling"]
    stored_flags = await asyncio.gather(
        *[_process(maker, dict(payload), src) for src in sources]
    )
    assert sum(1 for s in stored_flags if s) == 1
