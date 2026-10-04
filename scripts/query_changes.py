"""Query stored changes from CDMS (Phase 3 demo)."""

from __future__ import annotations

import argparse
import os
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        default=os.environ.get("CDMS_BASE_URL", "http://localhost:8000"),
    )
    parser.add_argument("--partnerSKU", default=None)
    parser.add_argument("--source", default=None)
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    params = {"limit": args.limit}
    if args.partnerSKU:
        params["partnerSKU"] = args.partnerSKU
    if args.source:
        params["source"] = args.source

    url = args.base.rstrip("/") + "/api/v1/changes"
    resp = httpx.get(url, params=params, timeout=10.0)
    print(f"GET {url} -> {resp.status_code}")
    print(resp.text)
    return 0 if resp.status_code < 400 else 1


if __name__ == "__main__":
    sys.exit(main())
