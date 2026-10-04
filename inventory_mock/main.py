from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from generator import build_initial_products
from mutation_engine import MutationEngine


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.products = build_initial_products()
    app.state.mutation_engine = MutationEngine(app.state.products)
    app.state.fault_enabled = False
    app.state.fault_status_code = 500
    app.state.mutation_engine.start()
    yield
    await app.state.mutation_engine.stop()


app = FastAPI(
    title="Vietful Inventory Mock",
    version="0.2.0",
    description="Faker-based mock of the Vietful inventory products API",
    lifespan=lifespan,
)


def _maybe_fault() -> None:
    if getattr(app.state, "fault_enabled", False):
        raise HTTPException(
            status_code=getattr(app.state, "fault_status_code", 500),
            detail="inventory fault injected",
        )


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "service": "inventory_mock",
        "product_count": len(getattr(app.state, "products", {}) or {}),
        "mutation_count": getattr(getattr(app.state, "mutation_engine", None), "mutation_count", 0),
    }


@app.get("/products")
async def list_products(
    pageIndex: int = 0,
    pageSize: int = 10,
    Keyword: str | None = None,
    PartnerSKUs: str | None = None,
    SKUs: str | None = None,
):
    _maybe_fault()
    products = list(app.state.products.values())
    if Keyword:
        key = Keyword.lower()
        products = [
            p
            for p in products
            if key in p["productName"].lower() or key in p["sku"].lower()
        ]
    if PartnerSKUs:
        allowed = {s.strip() for s in PartnerSKUs.split(",") if s.strip()}
        products = [p for p in products if p["partnerSKU"] in allowed]
    if SKUs:
        allowed = {s.strip() for s in SKUs.split(",") if s.strip()}
        products = [p for p in products if p["sku"] in allowed]

    start = pageIndex * pageSize
    end = start + pageSize
    return products[start:end]


@app.get("/products/{partnerSKU}")
async def get_product(partnerSKU: str):
    _maybe_fault()
    product = app.state.products.get(partnerSKU)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.post("/internal/mutate")
async def force_mutate(partnerSKU: str | None = None, count: int = 1):
    mutated = []
    for _ in range(max(1, min(count, 50))):
        product = app.state.mutation_engine.mutate_one(partnerSKU)
        if product:
            await app.state.mutation_engine.notify_cdms(product)
            mutated.append(product)
    return {"mutated": len(mutated), "items": mutated}


@app.post("/internal/fault")
async def set_fault(enabled: bool = False, status_code: int = 500):
    app.state.fault_enabled = enabled
    app.state.fault_status_code = status_code
    return {"fault_enabled": enabled, "status_code": status_code}
