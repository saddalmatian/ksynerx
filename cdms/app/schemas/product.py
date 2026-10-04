from pydantic import BaseModel


class ProcessResult(BaseModel):
    stored: bool
    external_id: str
    data_hash: str
    source: str
    change_id: int | None = None
    reason: str


class ProcessSummary(BaseModel):
    processed: int
    stored: int
    skipped: int
    errors: list[tuple[int, str]] = []
    results: list[ProcessResult] = []
