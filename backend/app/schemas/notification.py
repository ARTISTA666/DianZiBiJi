from datetime import datetime

from pydantic import BaseModel


class NotificationCreate(BaseModel):
    project_id: int | None = None
    title: str
    message: str = ""


class NotificationRead(BaseModel):
    id: int
    project_id: int | None = None
    title: str
    message: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}
