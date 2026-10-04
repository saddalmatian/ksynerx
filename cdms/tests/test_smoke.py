# Phase 1 smoke checks (no DB logic yet)

from fastapi.testclient import TestClient

from app.main import app


def test_healthz():
    client = TestClient(app)
    res = client.get("/healthz")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "CDMS"


def test_openapi_available():
    client = TestClient(app)
    res = client.get("/openapi.json")
    assert res.status_code == 200
    assert "CDMS" in res.json()["info"]["title"]
