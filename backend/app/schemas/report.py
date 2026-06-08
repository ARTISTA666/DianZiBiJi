from datetime import date

from pydantic import BaseModel


class ReportDraftRequest(BaseModel):
    report_type: str = "daily"  # daily | weekly
    project_id: int
    date_from: date | None = None
    date_to: date | None = None


class ReportDraft(BaseModel):
    title: str
    body: str
    source_note_ids: list[int] = []
