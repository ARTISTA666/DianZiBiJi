from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_project_access
from app.core.database import get_db
from app.models.user import User
from app.schemas.report import ReportDraft, ReportDraftRequest
from app.services.report import ReportDraftService

router = APIRouter(tags=["reports"])


@router.post("/api/reports/draft", response_model=ReportDraft)
def create_report_draft(
    payload: ReportDraftRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReportDraft:
    """生成实验报告草稿"""
    require_project_access(payload.project_id, db, user)
    try:
        result = ReportDraftService().create_draft(
            db,
            project_id=payload.project_id,
            report_type=payload.report_type,
            date_from=payload.date_from,
            date_to=payload.date_to,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ReportDraft(**result)
