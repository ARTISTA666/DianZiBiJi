from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import accessible_project_ids, get_current_user
from app.core.database import get_db
from app.models.user import User, UserRole
from app.schemas.dashboard import DashboardSummary
from app.services.dashboard import DashboardService

router = APIRouter(tags=["dashboard"])


@router.get("/api/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardSummary:
    """获取系统仪表盘统计数据"""
    project_ids = None if user.role == UserRole.SUPER_ADMIN else accessible_project_ids(db, user)
    data = DashboardService().summary(db, project_ids=project_ids, include_users=user.role == UserRole.SUPER_ADMIN)
    return DashboardSummary(**data)
