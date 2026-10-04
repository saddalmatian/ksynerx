"""Read APIs: stored changes + latest products."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.product import Product
from app.models.product_change import ProductChange

router = APIRouter(prefix="/api/v1", tags=["changes"])


@router.get("/changes")
async def list_changes(
    partnerSKU: str | None = None,
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    conditions = []
    if partnerSKU:
        conditions.append(ProductChange.product_external_id == partnerSKU)
    if source:
        conditions.append(ProductChange.source == source)

    stmt = (
        select(ProductChange)
        .where(*conditions)
        .order_by(ProductChange.id.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    total_stmt = select(func.count()).select_from(ProductChange).where(*conditions)
    total = int((await session.execute(total_stmt)).scalar_one())

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": row.id,
                "partnerSKU": row.product_external_id,
                "data_hash": row.data_hash,
                "source": row.source,
                "data": row.data,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


@router.get("/products/{external_id}")
async def get_latest_product(external_id: str, session: AsyncSession = Depends(get_db)):
    row = (
        await session.execute(select(Product).where(Product.external_id == external_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="product not found")
    return {
        "external_id": row.external_id,
        "data": row.data,
        "data_hash": row.data_hash,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
