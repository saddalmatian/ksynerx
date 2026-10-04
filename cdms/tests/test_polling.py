"""Phase 4 polling tests (HTTP fetch + schedule logic, no live Postgres)."""

from __future__ import annotations

from typing import Any

import pytest
import respx
from httpx import Response

from app.services.polling import (
    InventoryUnavailableError,
    fetch_products,
    get_poller_status,
    poll_once,
)

INVENTORY_URL = "http://inventory.test/products"


def _product(n: int, stock: int = 10) -> dict[str, Any]:
    return {
        "partnerSKU": f"P{n:03d}",
        "sku": f"SKU-{n:03d}",
        "productName": f"Product {n}",
        "stock": stock,
        "price": 100000 + n,
        "isActive": True,
    }


@respx.mock
async def test_fetch_pages_through_inventory():
    route = respx.get(INVENTORY_URL).mock(
        side_effect=[
            Response(200, json=[_product(1), _product(2)]),
            Response(200, json=[]),
        ]
    )
    items = await fetch_products("http://inventory.test", page_size=2)
    assert len(items) == 2
    assert route.call_count == 2


@respx.mock
async def test_fetch_raises_on_http_error():
    respx.get(INVENTORY_URL).mock(return_value=Response(500, text="boom"))
    with pytest.raises(InventoryUnavailableError):
        await fetch_products("http://inventory.test")


@respx.mock
async def test_fetch_raises_on_bad_payload():
    respx.get(INVENTORY_URL).mock(return_value=Response(200, json={"nope": True}))
    with pytest.raises(InventoryUnavailableError):
        await fetch_products("http://inventory.test")


@respx.mock
async def test_poll_once_handles_inventory_down(monkeypatch: pytest.MonkeyPatch):
    respx.get(INVENTORY_URL).mock(return_value=Response(503, text="down"))

    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "emulator_base_url", "http://inventory.test", raising=False)

    result = await poll_once()
    assert result["ok"] is False
    assert "inventory_unavailable" in (result["error"] or "")
    status = get_poller_status()
    assert status["last_error"]
    assert status["consecutive_errors"] >= 1
    assert status["running"] is False


@respx.mock
async def test_poll_once_empty_inventory(monkeypatch: pytest.MonkeyPatch):
    respx.get(INVENTORY_URL).mock(return_value=Response(200, json=[]))

    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "emulator_base_url", "http://inventory.test", raising=False)

    result = await poll_once()
    assert result["ok"] is True
    assert result["processed"] == 0
    assert result["stored"] == 0
    assert result["error"] is None
