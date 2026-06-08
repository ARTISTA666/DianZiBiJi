from pydantic import BaseModel


class OcrJobRequest(BaseModel):
    file_id: int


class OcrJobResult(BaseModel):
    file_id: int
    extracted_text: str
    source_ids: list[str] = []
