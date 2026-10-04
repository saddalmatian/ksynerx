from __future__ import annotations

from pydantic import BaseModel, Field


class ExcelRowError(BaseModel):
    row_number: int
    error: str


class ExcelImportResponse(BaseModel):
    status: str
    source: str = "excel"
    processed: int
    stored: int
    skipped: int
    invalid: int = 0
    errors: list[ExcelRowError] = Field(default_factory=list)
