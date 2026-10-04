# Phase 1 smoke checks for inventory mock (no DB)

from fastapi.testclient import TestClient

from main import app


def test_healthz():
    client = TestClient(app)
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_list_products():
    with TestClient(app) as client:
        res = client.get("/products", params={"pageSize": 5})
        assert res.status_code == 200
        items = res.json()
        assert len(items) == 5
        assert "partnerSKU" in items[0]
        assert "productName" in items[0]


def test_get_product_by_sku():
    with TestClient(app) as client:
        listed = client.get("/products", params={"pageSize": 1}).json()
        sku = listed[0]["partnerSKU"]
        res = client.get(f"/products/{sku}")
        assert res.status_code == 200
        assert res.json()["partnerSKU"] == sku
