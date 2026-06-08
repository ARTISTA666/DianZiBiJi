from datetime import date, datetime

from pydantic import BaseModel, Field


class NoteCreate(BaseModel):
    title: str
    experiment_type: str
    experiment_date: date | None = None
    template_id: int | None = None
    fixed_fields_json: dict = Field(default_factory=dict)
    content_json: dict = Field(default_factory=dict)


class NoteUpdate(BaseModel):
    title: str | None = None
    experiment_type: str | None = None
    experiment_date: date | None = None
    fixed_fields_json: dict | None = None
    content_json: dict | None = None
    change_summary: str | None = None


class NoteRead(BaseModel):
    id: int
    project_id: int
    template_id: int | None
    title: str
    experiment_type: str
    experiment_date: date | None
    owner_user_id: int
    status: str
    current_version_id: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NoteVersionRead(BaseModel):
    id: int
    note_id: int
    version_number: int
    fixed_fields_json: dict
    content_json: dict
    created_by: int
    change_summary: str | None
    is_locked: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ApprovalRequest(BaseModel):
    comment: str | None = None


class NoteApprovalRead(BaseModel):
    id: int
    note_id: int
    version_id: int
    reviewer_user_id: int
    action: str
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
