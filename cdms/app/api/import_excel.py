"""Excel file upload ingestion mechanism."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.excel import ExcelImportResponse, ExcelRowError
from app.services.change_processor import process_products
from app.services.excel_import import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES, parse_excel

router = APIRouter(prefix="/api/v1", tags=["excel"])


@router.post("/import/products", response_model=ExcelImportResponse)
async def import_products_excel(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
) -> ExcelImportResponse:
    filename = file.filename or ""
    if not any(filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=415,
            detail=f"unsupported file type; allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"file too large; max {MAX_UPLOAD_BYTES} bytes",
        )

    try:
        parsed = parse_excel(data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    errors: list[ExcelRowError] = [
        ExcelRowError(row_number=r.row_number, error=r.error or "invalid row")
        for r in parsed.rows
        if r.error or r.product is None
    ]
    valid_rows = [
        r for r in parsed.rows if not r.error and r.product is not None]
    row_numbers = [r.row_number for r in valid_rows]

    summary = await process_products(
        session,
        [r.product for r in valid_rows],
        source="excel",
    )

    # errors from the processor are (index in valid_rows, message)
    for index, message in summary.errors:
        errors.append(ExcelRowError(
            row_number=row_numbers[index], error=message))

    return ExcelImportResponse(
        status="accepted",
        processed=summary.processed,
        stored=summary.stored,
        skipped=summary.skipped,
        invalid=len(errors),
        errors=errors,
    )
