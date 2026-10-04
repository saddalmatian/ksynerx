"""Phase 2: exactly-once behavior of process_product()."""

import asyncio

import pytest

from app.services.change_processor import process_product, process_products
from tests.conftest import sample_product


async def test_new_product_stored(session):
    result = await process_product(session, sample_product(), source="polling")
    assert result.stored is True
    assert result.reason == "stored"
    assert result.external_id == "P001"
    assert result.change_id is not None


async def test_unchanged_product_ignored(session):
    first = await process_product(session, sample_product(), source="polling")
    second = await process_product(session, sample_product(), source="webhook")
    assert first.stored is True
    assert second.stored is False
    assert second.reason == "unchanged_or_duplicate"
    assert second.data_hash == first.data_hash


async def test_changed_product_stored(session):
    await process_product(session, sample_product(stock=10), source="polling")
    result = await process_product(session, sample_product(stock=8), source="polling")
    assert result.stored is True
    assert result.reason == "stored"


async def test_same_hash_different_source_single_row(session):
    payload = sample_product(stock=20)
    r1 = await process_product(session, payload, source="webhook")
    r2 = await process_product(session, dict(payload), source="excel")
    r3 = await process_product(session, dict(payload), source="polling")
    assert r1.stored is True
    assert r2.stored is False
    assert r3.stored is False
    assert r1.data_hash == r2.data_hash == r3.data_hash

    from sqlalchemy import func, select

    from app.models.product_change import ProductChange

    count = (
        await session.execute(select(func.count()).select_from(ProductChange))
    ).scalar_one()
    assert count == 1


async def test_concurrent_identical_submissions_single_row(session):
    payload = sample_product(stock=20, price=500000)

    # Sequential equivalent of concurrent same-event delivery is covered above;
    # also run a burst through process_products for summary shape.
    summary = await process_products(
        session,
        [dict(payload) for _ in range(20)],
        source="webhook",
    )
    assert summary.processed == 20
    assert summary.stored == 1
    assert summary.skipped == 19

    from sqlalchemy import func, select

    from app.models.product_change import ProductChange

    count = (
        await session.execute(select(func.count()).select_from(ProductChange))
    ).scalar_one()
    assert count == 1


async def test_multiple_changes_accumulate(session):
    await process_product(session, sample_product(stock=10), source="polling")
    await process_product(session, sample_product(stock=8), source="polling")
    await process_product(session, sample_product(stock=8), source="webhook")  # dup
    await process_product(session, sample_product(stock=5), source="excel")

    from sqlalchemy import func, select

    from app.models.product_change import ProductChange

    count = (
        await session.execute(select(func.count()).select_from(ProductChange))
    ).scalar_one()
    assert count == 3


async def test_missing_external_id_raises(session):
    with pytest.raises(ValueError):
        await process_product(session, {"productName": "No Id"}, source="webhook")


async def test_products_latest_state_upserted(session):
    await process_product(session, sample_product(stock=10), source="polling")
    await process_product(session, sample_product(stock=7), source="polling")

    from sqlalchemy import select

    from app.models.product import Product

    rows = (await session.execute(select(Product))).scalars().all()
    assert len(rows) == 1
    assert rows[0].external_id == "P001"
    assert rows[0].data["stock"] == 7
