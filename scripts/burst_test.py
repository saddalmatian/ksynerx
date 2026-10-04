"""Live exactly-once burst test against a running CDMS."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

import httpx


def make_payload(tag: str) -> dict:
    return {
        "partnerSKU": tag,
        "sku": f"SKU-{tag}",
        "productName": f"Burst product {tag}",
        "stock": 7,
        "price": 700000,
        "isActive": True,
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--cdms", default="http://localhost:8000")
    args = parser.parse_args()

    tag = f"BURST-{uuid.uuid4().hex[:8].upper()}"
    payload = make_payload(tag)

    async with httpx.AsyncClient(timeout=30) as client:
        print(f"[1] {args.n} concurrent identical webhook posts (tag={tag})")
        responses = await asyncio.gather(
            *[client.post(f"{args.cdms}/api/v1/webhooks/products", json=payload) for _ in range(args.n)]
        )
        statuses = [r.status_code for r in responses]
        assert all(s == 200 for s in statuses), f"non-200 statuses: {set(statuses)}"
        stored_sum = sum(r.json()["stored"] for r in responses)
        print(f"    sum(stored) reported = {stored_sum} (expect 1)")

        res = await client.get(
            f"{args.cdms}/api/v1/changes", params={"partnerSKU": tag, "limit": 100}
        )
        total = res.json()["total"]
        print(f"    rows in product_changes for {tag} = {total} (expect 1)")
        if stored_sum != 1 or total != 1:
            print("FAIL: exactly-once violated under concurrent identical writes")
            return 1

        print(f"[2] {args.n} concurrent distinct webhook posts")
        distinct_tags = [f"{tag}-D{i}" for i in range(args.n)]
        payloads = [make_payload(t) for t in distinct_tags]
        responses = await asyncio.gather(
            *[client.post(f"{args.cdms}/api/v1/webhooks/products", json=p) for p in payloads]
        )
        assert all(r.status_code == 200 for r in responses)
        stored_sum = sum(r.json()["stored"] for r in responses)
        print(f"    sum(stored) reported = {stored_sum} (expect {args.n})")

        res = await client.get(
            f"{args.cdms}/api/v1/changes", params={"partnerSKU": f"{tag}-D0", "limit": 10}
        )
        one_total = res.json()["total"]

        print("[3] cross-mechanism replay of identical payload")
        again = await client.post(f"{args.cdms}/api/v1/webhooks/products", json=payload)
        replay_stored = again.json()["stored"]

        res = await client.get(
            f"{args.cdms}/api/v1/changes", params={"partnerSKU": tag, "limit": 100}
        )
        final_total = res.json()["total"]
        print(f"    replay stored = {replay_stored} (expect 0), rows = {final_total} (expect 1)")

        ok = stored_sum == args.n and one_total == 1 and replay_stored == 0 and final_total == 1

    if ok:
        print("PASS: exactly-once holds under concurrent webhook burst")
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
