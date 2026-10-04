"""Phase 7 — failure-mode tests (DB down, bad payloads, poller error tracking)."""

from __future__ import annotations

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.db.database as dbmod
from app.main import app


def _dead_sessionmaker():
    from sqlalchemy.pool import NullPool

    engine = create_async_engine(
        "postgresql+asyncpg://cdms:cdms@127.0.0.1:1/cdms",
        connect_args={"timeout": 2},
        poolclass=NullPool,
    )
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def test_readyz_reports_db_down(monkeypatch: pytest.MonkeyPatch):
    dead_maker = _dead_sessionmaker()
    monkeypatch.setattr(dbmod, "SessionLocal", dead_maker)
    # No lifespan: readyz/healthz must work without init_db.
    client = TestClient(app, raise_server_exceptions=False)
    res = client.get("/readyz")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "not_ready"
    assert body["database"] == "down"
    # healthz must NOT depend on DB
    assert client.get("/healthz").json()["status"] == "ok"


def test_webhook_db_down_returns_5xx_not_200(monkeypatch: pytest.MonkeyPatch):
    dead_maker = _dead_sessionmaker()
    monkeypatch.setattr(dbmod, "SessionLocal", dead_maker)
    client = TestClient(app, raise_server_exceptions=False)
    res = client.post(
        "/api/v1/webhooks/products",
        json={"partnerSKU": "DBDOWN-1", "stock": 1},
    )
    assert res.status_code >= 500
    assert res.status_code != 200


def test_webhook_malformed_json_returns_400():
    client = TestClient(app, raise_server_exceptions=False)
    res = client.post(
        "/api/v1/webhooks/products",
        content=b"{not-json",
        headers={"content-type": "application/json"},
    )
    assert res.status_code == 400


def test_webhook_wrong_content_type_rejected():
    client = TestClient(app, raise_server_exceptions=False)
    res = client.post(
        "/api/v1/webhooks/products",
        content=b"partnerSKU=P1",
        headers={"content-type": "text/plain"},
    )
    assert res.status_code in (400, 415, 422)


@respx.mock
async def test_poller_error_counter_accumulates_then_recovers(monkeypatch: pytest.MonkeyPatch):
    from app.config import get_settings
    from app.services.polling import get_poller_status, poll_once

    settings = get_settings()
    monkeypatch.setattr(settings, "emulator_base_url", "http://inventory.test", raising=False)

    # Two consecutive failures (inventory 500)
    respx.get("http://inventory.test/products").mock(return_value=Response(500, text="boom"))
    await poll_once()
    await poll_once()
    status = get_poller_status()
    assert status["consecutive_errors"] >= 2
    assert status["last_error"]

    # Inventory recovers with empty catalog -> counter resets
    respx.get("http://inventory.test/products").mock(return_value=Response(200, json=[]))
    result = await poll_once()
    assert result["ok"] is True
    status = get_poller_status()
    assert status["consecutive_errors"] == 0
    assert status["last_error"] is None


@respx.mock
async def test_poller_survives_bad_payload(monkeypatch: pytest.MonkeyPatch):
    """Inventory returns garbage shape -> poll fails cleanly, no crash."""
    from app.config import get_settings
    from app.services.polling import get_poller_status, poll_once

    settings = get_settings()
    monkeypatch.setattr(settings, "emulator_base_url", "http://inventory.test", raising=False)

    respx.get("http://inventory.test/products").mock(return_value=Response(200, json={"unexpected": True}))
    result = await poll_once()
    assert result["ok"] is False
    assert get_poller_status()["running"] is False
