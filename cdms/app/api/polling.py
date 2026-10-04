"""Poller admin endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.services.polling import get_poller_status, poll_once

router = APIRouter(prefix="/api/v1", tags=["polling"])


@router.post("/polling/run")
async def trigger_poll():
    result = await poll_once()
    if not result["ok"] and result["processed"] == 0:
        raise HTTPException(status_code=503, detail=result["error"])
    return result


@router.get("/polling/status")
async def polling_status():
    return get_poller_status()
