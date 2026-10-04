"""Phase 5 Excel upload tests."""

from __future__ import annotations

import io
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.import_excel import router as excel_router
from app.db.database import get_db
from app.services.excel_import import parse_excel

HEADERS = ["partnerSKU", "sku", "productName", "color", "stock", "price", "isActive"]


def build_workbook(rows: list[list[Any]], headers: list[str] | None = None) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(headers if headers is not None else HEADERS)
    for row in rows:
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def sample_rows() -> list[list[Any]]:
    return [
        ["P001", "SKU-001", "Keyboard", "Black", 10, 499000, True],
        ["P002", "SKU-002", "Mouse", "White", 25, 199000, "TRUE"],
        ["P003", "SKU-003", "Headset", "Blue", 5, 299000, 1],
    ]


@pytest.fixture
def client(session: AsyncSession) -> TestClient:
    app = FastAPI()
    app.include_router(excel_router)

    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_parse_valid_workbook():
    parsed = parse_excel(build_workbook(sample_rows()))
    assert len(parsed.products) == 3
    assert not parsed.errors
    first = parsed.products[0]
    assert first["partnerSKU"] == "P001"
    assert first["stock"] == 10
    assert first["price"] == 499000
    assert first["isActive"] is True


def test_parse_header_aliases_and_coercion():
    rows = [
        ["P10", "KB-10", "Alias Product", "10", "499000.5", "yes"],
    ]
    headers = ["Partner SKU", "sku", "Name", "Quantity", "Price", "Is Active"]
    parsed = parse_excel(build_workbook(rows, headers=headers))
    product = parsed.products[0]
    assert product["partnerSKU"] == "P10"
    assert product["stock"] == 10
    assert product["price"] == 499000.5
    assert product["isActive"] is True
    assert product["productName"] == "Alias Product"


def test_parse_skips_rows_missing_id():
    rows = [
        ["P001", "SKU-1", "OK", "Black", 1, 100, True],
        [None, None, "No ids", "Red", 2, 200, True],
        ["", "  ", "Blank ids", "Blue", 3, 300, True],
    ]
    parsed = parse_excel(build_workbook(rows))
    assert len(parsed.products) == 1
    assert len(parsed.errors) == 2
    assert all("missing partnerSKU/sku" in e.error for e in parsed.errors)


def test_parse_empty_and_invalid_files():
    with pytest.raises(ValueError, match="empty file"):
        parse_excel(b"")
    with pytest.raises(ValueError, match="invalid xlsx"):
        parse_excel(b"not-an-xlsx")


def test_parse_unrecognized_headers():
    data = build_workbook([["a", "b"]], headers=["foo", "bar"])
    with pytest.raises(ValueError, match="no recognizable columns"):
        parse_excel(data)


def test_http_upload_stores_and_dedups(client: TestClient):
    data = build_workbook(sample_rows())
    res = client.post(
        "/api/v1/import/products",
        files={"file": ("products.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "excel"
    assert body["stored"] == 3
    assert body["skipped"] == 0
    assert body["invalid"] == 0

    # Re-upload identical file -> all duplicates skipped
    res2 = client.post(
        "/api/v1/import/products",
        files={"file": ("products.xlsx", data, "application/octet-stream")},
    )
    body2 = res2.json()
    assert body2["stored"] == 0
    assert body2["skipped"] == 3


def test_http_upload_partial_invalid_rows(client: TestClient):
    rows = sample_rows() + [[None, None, "Bad row", "Green", 1, 100, True]]
    data = build_workbook(rows)
    res = client.post(
        "/api/v1/import/products",
        files={"file": ("products.xlsx", data, "application/octet-stream")},
    )
    body = res.json()
    assert res.status_code == 200
    assert body["stored"] == 3
    assert body["invalid"] == 1
    assert body["errors"][0]["row_number"] == 5


def test_http_upload_rejects_wrong_extension(client: TestClient):
    res = client.post(
        "/api/v1/import/products",
        files={"file": ("products.csv", b"a,b", "text/csv")},
    )
    assert res.status_code == 415


def test_http_upload_rejects_empty_file(client: TestClient):
    res = client.post(
        "/api/v1/import/products",
        files={"file": ("products.xlsx", b"", "application/octet-stream")},
    )
    assert res.status_code == 400


def test_http_upload_rejects_corrupt_file(client: TestClient):
    res = client.post(
        "/api/v1/import/products",
        files={"file": ("products.xlsx", b"garbage-bytes", "application/octet-stream")},
    )
    assert res.status_code == 422
