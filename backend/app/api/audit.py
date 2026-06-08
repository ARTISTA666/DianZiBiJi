from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.audit import AuditLog
from app.models.user import User

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("")
def list_audit_logs(
    actor_user_id: int | None = None,
    project_id: int | None = None,
    action: str | None = None,
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[dict]:
    query = db.query(AuditLog)
    if actor_user_id is not None:
        query = query.filter(AuditLog.actor_user_id == actor_user_id)
    if project_id is not None:
        query = query.filter(AuditLog.project_id == project_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if date_from is not None:
        query = query.filter(AuditLog.created_at >= date_from)
    if date_to is not None:
        query = query.filter(AuditLog.created_at <= date_to)
    logs = query.order_by(AuditLog.created_at.desc()).limit(200).all()
    return [
        {
            "id": log.id,
            "actor_user_id": log.actor_user_id,
            "project_id": log.project_id,
            "action": log.action,
            "target_type": log.target_type,
            "target_id": log.target_id,
            "detail_json": log.detail_json,
            "created_at": log.created_at,
        }
        for log in logs
    ]
