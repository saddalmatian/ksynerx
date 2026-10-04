"""Periodic product mutations to simulate inventory change traffic."""

from __future__ import annotations

import asyncio
import logging
import os
import random
from typing import Any

import httpx

logger = logging.getLogger("inventory_mock.mutation")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class MutationEngine:
    def __init__(
        self,
        products: dict[str, dict],
        *,
        interval_seconds: float = 10.0,
        batch_size: int = 3,
        callback_enabled: bool | None = None,
        cdms_base_url: str | None = None,
        webhook_secret: str | None = None,
    ) -> None:
        self.products = products
        self.interval_seconds = interval_seconds
        self.batch_size = batch_size
        self.callback_enabled = (
            callback_enabled
            if callback_enabled is not None
            else _env_bool("WEBHOOK_CALLBACK_ENABLED", False)
        )
        self.cdms_base_url = (
            cdms_base_url
            or os.environ.get("CDMS_BASE_URL", "http://localhost:8000")
        ).rstrip("/")
        self.webhook_secret = webhook_secret if webhook_secret is not None else os.environ.get(
            "WEBHOOK_SECRET", ""
        )
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.mutation_count = 0

    def mutate_one(self, partner_sku: str | None = None) -> dict[str, Any] | None:
        keys = list(self.products.keys())
        if not keys:
            return None
        sku = partner_sku or random.choice(keys)
        product = self.products.get(sku)
        if product is None:
            return None

        field = random.choice(["stock", "price", "productName", "color"])
        if field == "stock":
            product["stock"] = max(0, int(product.get("stock", 0)) + random.randint(-5, 10))
        elif field == "price":
            product["price"] = max(1000, int(product.get("price", 1000)) + random.randint(-20000, 30000))
        elif field == "productName":
            from faker import Faker

            fake = Faker("vi_VN")
            product["productName"] = fake.catch_phrase().title()
        elif field == "color":
            from faker import Faker

            fake = Faker("vi_VN")
            product["color"] = fake.color_name()

        self.mutation_count += 1
        return dict(product)

    async def notify_cdms(self, product: dict[str, Any]) -> None:
        if not self.callback_enabled:
            return
        url = f"{self.cdms_base_url}/api/v1/webhooks/products"
        payload = {
            "partnerSKU": product.get("partnerSKU"),
            "sku": product.get("sku"),
            "productName": product.get("productName"),
            "color": product.get("color"),
            "size": product.get("size"),
            "isActive": product.get("isActive"),
            "price": product.get("price"),
            "stock": product.get("stock"),
        }
        headers = {"content-type": "application/json"}
        if self.webhook_secret:
            import base64
            import hashlib
            import hmac as hmac_mod

            body = __import__("json").dumps(payload, separators=(",", ":")).encode("utf-8")
            digest = hmac_mod.new(
                self.webhook_secret.encode("utf-8"), body, hashlib.sha256
            ).digest()
            headers["x-vf-hmacsha256"] = base64.b64encode(digest).decode("ascii")
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(url, content=body, headers=headers)
                    logger.info("callback status=%s sku=%s", resp.status_code, payload.get("partnerSKU"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("callback failed: %s", exc)
            return
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(url, json=payload)
                logger.info("callback status=%s sku=%s", resp.status_code, payload.get("partnerSKU"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("callback failed: %s", exc)

    async def tick(self) -> list[dict[str, Any]]:
        mutated: list[dict[str, Any]] = []
        for _ in range(self.batch_size):
            product = self.mutate_one()
            if product:
                mutated.append(product)
                await self.notify_cdms(product)
        return mutated

    async def _run(self) -> None:
        logger.info(
            "mutation engine started interval=%ss callback=%s",
            self.interval_seconds,
            self.callback_enabled,
        )
        while not self._stop.is_set():
            try:
                await self.tick()
            except Exception as exc:  # noqa: BLE001
                logger.warning("mutation tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval_seconds)
            except asyncio.TimeoutError:
                continue

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._stop.clear()
            self._task = asyncio.get_event_loop().create_task(self._run())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task
            self._task = None
