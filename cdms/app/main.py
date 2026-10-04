from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from sqlalchemy import text

from app.api.changes import router as changes_router
from app.api.import_excel import router as excel_router
from app.api.polling import router as polling_router
from app.api.webhook import router as webhook_router
from app.config import get_settings
from app.db.database import init_db
from app.services.polling import poll_once

settings = get_settings()
scheduler = AsyncIOScheduler(timezone="UTC")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    scheduler.add_job(
        poll_once,
        "interval",
        seconds=settings.poll_interval_seconds,
        id="inventory_poll",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    description="Change Data Management Service prototype",
    lifespan=lifespan,
)

app.include_router(webhook_router)
app.include_router(changes_router)
app.include_router(polling_router)
app.include_router(excel_router)


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "service": settings.app_name}


@app.get("/readyz")
async def readyz():
    from app.db.database import SessionLocal

    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready", "database": "up"}
    except Exception as exc:  # noqa: BLE001
        return {"status": "not_ready", "database": "down", "detail": str(exc)}
