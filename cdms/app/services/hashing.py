"""Canonical hashing for exactly-once change detection."""

from __future__ import annotations

import hashlib
import json
from typing import Any

CANONICAL_FIELDS: tuple[str, ...] = (
    "sku",
    "partnerSKU",
    "productName",
    "color",
    "size",
    "description",
    "assetType",
    "isActive",
    "price",
    "stock",
)

EXCLUDED_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "external_id",
        "productId",
        "timestamp",
        "received_at",
        "created_at",
        "updated_at",
        "source",
        "event",
        "errorCode",
        "errorMessage",
    }
)


def normalize_product(product: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}

    ignored_fields = EXCLUDED_FIELDS | {
        "units",
        "categories",
        "productBundles",
        "productBarcodes",
    }

    for key, value in product.items():
        if value is None or key in ignored_fields:
            continue

        if key in CANONICAL_FIELDS or isinstance(value, (str, int, float, bool)):
            normalized[key] = value

    return normalized


def canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    )


def hash_payload(data: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


def extract_external_id(product: dict[str, Any]) -> str:
    for key in ("external_id", "partnerSKU", "id", "sku"):
        value = product.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    raise ValueError(
        "product has no usable external id (external_id/partnerSKU/id/sku)"
    )
