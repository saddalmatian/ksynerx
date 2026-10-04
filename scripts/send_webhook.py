"""Send a product webhook to CDMS (Phase 3 demo)."""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="POST a product change to CDMS webhook")
    parser.add_argument("--url", default=os.environ.get("CDMS_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--partnerSKU", default="P001")
    parser.add_argument("--stock", type=int, default=15)
    parser.add_argument("--price", type=int, default=500000)
    parser.add_argument("--name", default="Wireless Keyboard")
    parser.add_argument("--sku", default="SKU-001")
    parser.add_argument("--hmac-secret", default=os.environ.get("WEBHOOK_SECRET", ""))
    parser.add_argument(
        "--path",
        default="/api/v1/webhooks/products",
        help="CDMS path (default webhook path)",
    )
    args = parser.parse_args()

    url = args.url
    base = url.rstrip("/")
    if not (base.endswith(args.path) or base.endswith("products") or "webhooks" in url):
        url = base + args.path

    payload = {
        "partnerSKU": args.partnerSKU,
        "sku": args.sku,
        "productName": args.name,
        "color": "Black",
        "size": "Full",
        "isActive": True,
        "price": args.price,
        "stock": args.stock,
    }

    headers = {"content-type": "application/json"}
    if args.hmac_secret:
        import base64
        import hashlib
        import hmac as hmac_mod

        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        digest = hmac_mod.new(
            args.hmac_secret.encode("utf-8"), body, hashlib.sha256
        ).digest()
        headers["x-vf-hmacsha256"] = base64.b64encode(digest).decode("ascii")
        print(f"POST {url}")
        print(f"payload: {payload}")
        resp = httpx.post(url, content=body, headers=headers, timeout=10.0)
    else:
        print(f"POST {url}")
        print(f"payload: {payload}")
        resp = httpx.post(url, json=payload, headers=headers, timeout=10.0)

    print(f"status: {resp.status_code}")
    print(resp.text)
    return 0 if resp.status_code < 400 else 1


if __name__ == "__main__":
    sys.exit(main())
