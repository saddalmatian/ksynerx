"""Hash / normalize unit tests (no database)."""

from app.services.hashing import (
    canonical_json,
    extract_external_id,
    hash_payload,
    normalize_product,
)


def test_normalize_sorts_and_drops_excluded():
    data = normalize_product(
        {
            "partnerSKU": "P1",
            "stock": 5,
            "timestamp": 123,
            "id": 99,
            "productName": "X",
        }
    )
    assert "timestamp" not in data
    assert "id" not in data
    assert data["stock"] == 5
    assert canonical_json(data) == canonical_json(dict(sorted(data.items())))


def test_hash_stable_across_key_order():
    a = {"partnerSKU": "P1", "stock": 5, "productName": "X"}
    b = {"productName": "X", "stock": 5, "partnerSKU": "P1"}
    assert hash_payload(normalize_product(a)) == hash_payload(normalize_product(b))


def test_hash_changes_with_value():
    a = normalize_product({"partnerSKU": "P1", "stock": 5})
    b = normalize_product({"partnerSKU": "P1", "stock": 6})
    assert hash_payload(a) != hash_payload(b)


def test_extract_external_id_prefers_partner_sku():
    assert extract_external_id({"partnerSKU": "P001", "id": 1}) == "P001"
    assert extract_external_id({"id": 42}) == "42"
