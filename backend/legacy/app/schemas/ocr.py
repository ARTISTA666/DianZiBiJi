from datetime import datetime

from pydantic import BaseModel, Field


class OcrJobRequest(BaseModel):
    file_id: int


class OcrJobResult(BaseModel):
    ocr_result_id: int
    file_id: int
    extracted_text: str
    raw_text: str
    source_ids: list[str] = Field(default_factory=list)
    character_count: int
    truncated: bool = False
    extraction_method: str
    review_status: str
    created_by: int
    reviewed_by: int | None = None
    created_at: datetime
    reviewed_at: datetime | None = None


class OcrCorrectionRequest(BaseModel):
    corrected_text: str = Field(min_length=1, max_length=2_000_000)
