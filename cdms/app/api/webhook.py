"""Webhook ingestion mechanism."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import get_db
from app.schemas.webhook import WebhookEnvelope, WebhookProduct, WebhookResponse
from app.services.change_processor import process_products
from app.services.webhook_auth import verify_webhook_signature

router = APIRouter(prefix="/api/v1", tags=["webhooks"])


def _extract_products(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [WebhookProduct.model_validate(p).to_processor_dict() for p in payload]
    if isinstance(payload, dict):
        if "items" in payload or "product" in payload:
            envelope = WebhookEnvelope.model_validate(payload)
            if envelope.items:
                return [item.to_processor_dict() for item in envelope.items]
            if envelope.product:
                return [envelope.product.to_processor_dict()]
            raise ValueError("envelope has no items or product")
        return [WebhookProduct.model_validate(payload).to_processor_dict()]
    raise ValueError("unsupported webhook payload type")


@router.post("/webhooks/products", response_model=WebhookResponse)
async def receive_product_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> WebhookResponse:
    settings = get_settings()
    body = await request.body()
    signature = request.headers.get("x-vf-hmacsha256") or request.headers.get(
        "X-Vf-HmacSha256"
    )
    if not verify_webhook_signature(body, settings.webhook_secret, signature):
        raise HTTPException(
            status_code=401, detail="invalid webhook signature")

    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=400, detail="invalid JSON body") from exc

    try:
        products = _extract_products(payload)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    summary = await process_products(session, products, source="webhook")

    if summary.errors:
        raise HTTPException(status_code=422, detail=summary.errors[0][1])

    return WebhookResponse(
        status="accepted",
        processed=summary.processed,
        stored=summary.stored,
        skipped=summary.skipped,
        results=summary.results,
    )
