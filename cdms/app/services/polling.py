"""Scheduled polling of the inventory mock."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.db.database import SessionLocal
from app.services.change_processor import process_products

logger = logging.getLogger("cdms.polling")

poller_status: dict[str, Any] = {
    "running": False,
    "last_run_at": None,
    "last_result": None,
    "last_error": None,
    "runs": 0,
    "consecutive_errors": 0,
}


class InventoryUnavailableError(RuntimeError):
    pass


def get_poller_status() -> dict[str, Any]:
    return dict(poller_status)


async def fetch_products(
    base_url: str, page_size: int = 100, max_pages: int = 50
) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=10.0) as client:
        for page_index in range(max_pages):
            try:
                resp = await client.get(
                    f"{base_url.rstrip('/')}/products",
                    params={"pageIndex": page_index, "pageSize": page_size},
                )
                resp.raise_for_status()
                items = resp.json()
            except httpx.HTTPError as exc:
                raise InventoryUnavailableError(str(exc)) from exc
            if not isinstance(items, list):
                raise InventoryUnavailableError(
                    f"unexpected products payload type: {type(items).__name__}"
                )
            products.extend(items)
            if len(items) < page_size:
                break
    return products


async def poll_once(page_size: int = 100) -> dict[str, Any]:
    settings = get_settings()
    poller_status["running"] = True
    started = datetime.now(timezone.utc)
    stored = 0
    skipped = 0
    processed = 0
    error: str | None = None

    try:
        products = await fetch_products(settings.emulator_base_url, page_size=page_size)
        async with SessionLocal() as session:
            batch = await process_products(session, products, source="polling")
            processed = batch.processed
            stored = batch.stored
            skipped = batch.skipped
    except InventoryUnavailableError as exc:
        error = f"inventory_unavailable: {exc}"
        logger.warning("poll failed: %s", error)
        poller_status["consecutive_errors"] += 1
    except Exception as exc:  # noqa: BLE001
        error = f"poll_error: {exc}"
        logger.exception("poll failed unexpectedly")
        poller_status["consecutive_errors"] += 1
    finally:
        poller_status["running"] = False
        poller_status["runs"] += 1
        poller_status["last_run_at"] = started.isoformat()

    summary = {
        "ok": error is None,
        "processed": processed,
        "stored": stored,
        "skipped": skipped,
        "error": error,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    if error is None:
        poller_status["consecutive_errors"] = 0
        poller_status["last_error"] = None
        logger.info(
            "poll ok processed=%s stored=%s skipped=%s", processed, stored, skipped
        )
    else:
        poller_status["last_error"] = error
    poller_status["last_result"] = summary
    return summary
