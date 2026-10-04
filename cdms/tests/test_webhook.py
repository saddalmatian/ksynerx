"""Phase 3 webhook tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.webhook import router as webhook_router
from app.db.database import get_db
from app.services.webhook_auth import (
    compute_hmac_sha256_base64,
    verify_webhook_signature,
)
from tests.conftest import sample_product


@pytest.fixture
def client(session: AsyncSession) -> TestClient:
    app = FastAPI()
    app.include_router(webhook_router)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_hmac_helper_roundtrip():
    body = b'{"partnerSKU":"P1","stock":5}'
    secret = "s3cret"
    sig = compute_hmac_sha256_base64(body, secret)
    assert verify_webhook_signature(body, secret, sig) is True
    assert verify_webhook_signature(body, secret, "bad") is False
    assert verify_webhook_signature(body, None, None) is True
    assert verify_webhook_signature(body, secret, None) is False


def test_webhook_single_product_stored(client: TestClient):
    payload = sample_product()
    res = client.post("/api/v1/webhooks/products", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["processed"] == 1
    assert body["stored"] == 1
    assert body["results"][0]["stored"] is True


def test_webhook_duplicate_skipped(client: TestClient):
    payload = sample_product()
    first = client.post("/api/v1/webhooks/products", json=payload).json()
    second = client.post("/api/v1/webhooks/products", json=payload).json()
    assert first["stored"] == 1
    assert second["stored"] == 0
    assert second["skipped"] == 1
    assert second["results"][0]["reason"] == "unchanged_or_duplicate"


def test_webhook_envelope_items(client: TestClient):
    envelope = {
        "event": "INV_CHANGED",
        "id": "evt-1",
        "timestamp": 1710000000,
        "items": [
            {"partnerSKU": "P100", "sku": "SKU-100", "productName": "Mouse", "stock": 3},
            {"partnerSKU": "P101", "sku": "SKU-101", "productName": "Headset", "stock": 2},
        ],
    }
    res = client.post("/api/v1/webhooks/products", json=envelope)
    assert res.status_code == 200
    body = res.json()
    assert body["processed"] == 2
    assert body["stored"] == 2

    # replay
    res2 = client.post("/api/v1/webhooks/products", json=envelope)
    assert res2.json()["stored"] == 0


def test_webhook_list_payload(client: TestClient):
    payload = [sample_product(partnerSKU="A1"), sample_product(partnerSKU="A2", stock=1)]
    res = client.post("/api/v1/webhooks/products", json=payload)
    assert res.status_code == 200
    assert res.json()["stored"] == 2


def test_webhook_invalid_missing_id(client: TestClient):
    res = client.post("/api/v1/webhooks/products", json={"productName": "No id"})
    assert res.status_code == 422


def test_webhook_invalid_envelope(client: TestClient):
    res = client.post("/api/v1/webhooks/products", json={"event": "X"})
    assert res.status_code == 422


def test_webhook_rejects_bad_hmac(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "webhook_secret", "topsecret", raising=False)

    res = client.post(
        "/api/v1/webhooks/products",
        json=sample_product(),
        headers={"x-vf-hmacsha256": "d3Jvbmc="},
    )
    assert res.status_code == 401

    body = (
        b'{"partnerSKU":"P001","sku":"SKU-001","productName":"Wireless Keyboard",'
        b'"color":"Black","size":"Full","isActive":true,"price":499000,"stock":10}'
    )
    sig = compute_hmac_sha256_base64(body, "topsecret")
    res2 = client.post(
        "/api/v1/webhooks/products",
        content=body,
        headers={
            "x-vf-hmacsha256": sig,
            "content-type": "application/json",
        },
    )
    assert res2.status_code in (200, 422)
    if res2.status_code == 200:
        assert res2.json()["stored"] in (0, 1)
