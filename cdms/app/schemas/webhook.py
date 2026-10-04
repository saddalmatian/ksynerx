from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.product import ProcessResult


class _ProductFields(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | int | None = None
    partnerSKU: str | None = None
    sku: str | None = None
    productName: str | None = None
    color: str | None = None
    size: str | None = None
    isActive: bool | None = None
    price: int | float | None = None
    stock: int | float | None = None

    def _base_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


class WebhookProduct(_ProductFields):
    external_id: str | None = None
    name: str | None = None
    description: str | None = None
    assetType: str | None = None

    def to_processor_dict(self) -> dict[str, Any]:
        data = self._base_dict()
        if self.partnerSKU:
            data["partnerSKU"] = self.partnerSKU
        elif self.external_id:
            data["external_id"] = self.external_id
        elif self.id is not None:
            data["external_id"] = str(self.id)
        if self.name and not self.productName:
            data["productName"] = self.name
        return data


class WebhookItem(_ProductFields):
    changeQty: int | None = None
    changedReason: str | None = None

    def to_processor_dict(self) -> dict[str, Any]:
        data = self._base_dict()
        if self.partnerSKU:
            data["partnerSKU"] = self.partnerSKU
        elif self.id is not None:
            data["external_id"] = str(self.id)
        if self.changeQty is not None and "stock" not in data:
            data["stock"] = self.changeQty
        return data


class WebhookEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event: str | None = None
    id: str | None = None
    timestamp: int | str | None = None
    errorCode: str | None = None
    errorMessage: str | None = None
    warehouseCode: str | None = None
    changedReason: str | None = None
    items: list[WebhookItem] | None = None
    product: WebhookProduct | None = None

    @model_validator(mode="after")
    def require_content(self) -> "WebhookEnvelope":
        if not self.items and not self.product:
            raise ValueError("webhook envelope must include items[] or product")
        return self


class WebhookResponse(BaseModel):
    status: str
    source: str = "webhook"
    processed: int
    stored: int
    skipped: int
    results: list[ProcessResult] = Field(default_factory=list)
