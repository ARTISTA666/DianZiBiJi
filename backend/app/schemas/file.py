from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class FileReviewRequest(BaseModel):
    action: Literal["approve", "reject"]
    comment: str | None = None


class FileUpdate(BaseModel):
    original_filename: str | None = None


class FileRead(BaseModel):
    id: int
    project_id: int
    note_id: int | None
    uploaded_by: int
    file_category: str
    original_filename: str
    mime_type: str | None
    file_size: int
    file_hash: str
    status: str
    knowledge_sync_status: str
    knowledge_synced_at: datetime | None
    knowledge_sync_message: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
