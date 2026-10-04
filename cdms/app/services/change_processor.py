"""Single write path for all ingestion mechanisms."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.product_change import ProductChange
from app.schemas.product import ProcessResult, ProcessSummary
from app.services.hashing import extract_external_id, hash_payload, normalize_product


async def process_product(
    session: AsyncSession,
    product: dict[str, Any],
    source: str,
) -> ProcessResult:
    external_id = extract_external_id(product)
    data = normalize_product(product)
    data_hash = hash_payload(data)

    # sqlite in the tests, postgres in docker - same ON CONFLICT in both
    if session.get_bind().dialect.name == "postgresql":
        insert = pg_insert
    else:
        insert = sqlite_insert

    # 1) try to add the change, ignore it if this state was stored before
    try:
        stmt = (
            insert(ProductChange)
            .values(
                product_external_id=external_id,
                data_hash=data_hash,
                data=data,
                source=source,
            )
            .on_conflict_do_nothing(index_elements=["product_external_id", "data_hash"])
        )
        result = await session.execute(stmt)
        stored = bool(result.rowcount and result.rowcount > 0)
    except IntegrityError:
        await session.rollback()
        return ProcessResult(
            stored=False,
            external_id=external_id,
            data_hash=data_hash,
            source=source,
            reason="duplicate_or_conflict",
        )

    if not stored:
        await session.rollback()
        return ProcessResult(
            stored=False,
            external_id=external_id,
            data_hash=data_hash,
            source=source,
            reason="unchanged_or_duplicate",
        )

    # 2) new change -> keep the latest state of the product in sync
    stmt = (
        insert(Product)
        .values(external_id=external_id, data=data, data_hash=data_hash)
        .on_conflict_do_update(
            index_elements=["external_id"],
            set_={
                "data": data,
                "data_hash": data_hash,
                "updated_at": func.now(),
            },
        )
    )
    await session.execute(stmt)

    row = await session.execute(
        select(ProductChange.id)
        .where(
            ProductChange.product_external_id == external_id,
            ProductChange.data_hash == data_hash,
        )
        .limit(1)
    )
    change_id = row.scalar_one_or_none()

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return ProcessResult(
            stored=False,
            external_id=external_id,
            data_hash=data_hash,
            source=source,
            reason="duplicate_on_commit",
        )

    return ProcessResult(
        stored=True,
        external_id=external_id,
        data_hash=data_hash,
        source=source,
        change_id=change_id,
        reason="stored",
    )


async def process_products(
    session: AsyncSession,
    products: list[dict[str, Any]],
    source: str,
) -> ProcessSummary:
    """Runs every product through process_product().

    Rows without a usable id are skipped and returned in summary.errors as
    (index, message) so the caller can decide what to do with them.
    """
    stored = 0
    skipped = 0
    results: list[ProcessResult] = []
    errors: list[tuple[int, str]] = []

    for index, product in enumerate(products):
        try:
            result = await process_product(session, product, source=source)
        except ValueError as exc:
            skipped += 1
            errors.append((index, str(exc)))
            continue

        results.append(result)
        if result.stored:
            stored += 1
        else:
            skipped += 1

    return ProcessSummary(
        processed=len(products),
        stored=stored,
        skipped=skipped,
        errors=errors,
        results=results,
    )
