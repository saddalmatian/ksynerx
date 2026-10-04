"""Spike test: ramp concurrent webhook load, report latency and errors."""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
import uuid

import httpx


def make_payload(tag: str, i: int) -> dict:
    return {
        "partnerSKU": f"{tag}-{i}",
        "sku": f"SKU-{tag}-{i}",
        "productName": f"Spike product {i}",
        "stock": i % 100,
        "price": 100000 + i,
        "isActive": True,
    }


async def burst(client: httpx.AsyncClient, url: str, payloads: list[dict]) -> tuple[list[float], list[int], int]:
    latencies: list[float] = []
    statuses: list[int] = []
    errors = 0

    async def one(payload: dict) -> None:
        nonlocal errors
        start = time.perf_counter()
        try:
            res = await client.post(url, json=payload)
            statuses.append(res.status_code)
            if res.status_code != 200:
                errors += 1
        except Exception:  # noqa: BLE001
            errors += 1
            statuses.append(0)
        finally:
            latencies.append((time.perf_counter() - start) * 1000)

    await asyncio.gather(*[one(p) for p in payloads])
    return latencies, statuses, errors


def pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((p / 100) * (len(ordered) - 1))))
    return ordered[index]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdms", default="http://localhost:8000")
    parser.add_argument("--ramp", default="50,100,250,500")
    args = parser.parse_args()
    levels = [int(x) for x in args.ramp.split(",") if x.strip()]

    tag = f"SPIKE-{uuid.uuid4().hex[:8].upper()}"
    webhook_url = f"{args.cdms}/api/v1/webhooks/products"
    total_expected = 0
    all_latencies: list[float] = []

    async with httpx.AsyncClient(timeout=60) as client:
        for level in levels:
            payloads = [make_payload(tag, i) for i in range(total_expected, total_expected + level)]
            wall_start = time.perf_counter()
            latencies, statuses, errors = await burst(client, webhook_url, payloads)
            wall = time.perf_counter() - wall_start
            all_latencies.extend(latencies)
            ok = sum(1 for s in statuses if s == 200)
            rps = level / wall if wall else 0
            print(
                f"level={level:5d} ok={ok:5d} errors={errors:3d} "
                f"wall={wall:6.2f}s rps={rps:7.1f} "
                f"p50={pct(latencies, 50):7.1f}ms p95={pct(latencies, 95):7.1f}ms "
                f"max={max(latencies):7.1f}ms"
            )
            if errors:
                print(f"  WARN: {errors} failed requests at level {level}")
            total_expected += level

        res = await client.get(
            f"{args.cdms}/api/v1/changes",
            params={"partnerSKU": f"{tag}-0", "limit": 5},
        )
        first_ok = res.json()["total"] == 1
        res = await client.get(
            f"{args.cdms}/api/v1/changes",
            params={"partnerSKU": f"{tag}-{total_expected - 1}", "limit": 5},
        )
        last_ok = res.json()["total"] == 1

        health = await client.get(f"{args.cdms}/healthz")
        ready = await client.get(f"{args.cdms}/readyz")
        healthy = health.status_code == 200 and ready.json().get("database") == "up"

        replay_payloads = [make_payload(tag, i) for i in range(min(50, total_expected))]
        _, _, replay_errors = await burst(client, webhook_url, replay_payloads)

    print(
        f"aggregate: total={total_expected} p50={pct(all_latencies, 50):.1f}ms "
        f"p95={pct(all_latencies, 95):.1f}ms p99={pct(all_latencies, 99):.1f}ms "
        f"mean={statistics.fmean(all_latencies):.1f}ms"
    )
    print(f"integrity: first={first_ok} last={last_ok} healthy={healthy} replay_errors={replay_errors}")

    if first_ok and last_ok and healthy and replay_errors == 0:
        print("PASS: spike absorbed, service healthy, data intact")
        return 0
    print("FAIL")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
