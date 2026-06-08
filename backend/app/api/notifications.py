from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import accessible_project_ids, can_write_project, get_current_user, require_admin, require_project_access
from app.core.database import get_db
from app.models.user import User
from app.schemas.notification import NotificationCreate, NotificationRead
from app.services.notification import NotificationService

router = APIRouter(tags=["notifications"])


@router.post("/api/notifications", response_model=NotificationRead)
def publish_notification(
    payload: NotificationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationRead:
    """发布通知"""
    if payload.project_id is None:
        require_admin(user)
    else:
        require_project_access(payload.project_id, db, user)
        if not can_write_project(db, user, payload.project_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Write permission required")
    record = NotificationService().publish(db, title=payload.title, message=payload.message, project_id=payload.project_id)
    db.commit()
    db.refresh(record)
    return NotificationRead.model_validate(record)


@router.get("/api/notifications", response_model=list[NotificationRead])
def list_notifications(
    project_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[NotificationRead]:
    """获取最近的通知列表"""
    if project_id is not None:
        require_project_access(project_id, db, user)
        records = NotificationService().list_recent(db, project_id=project_id)
    else:
        records = NotificationService().list_recent(db, project_ids=accessible_project_ids(db, user))
    return [NotificationRead.model_validate(r) for r in records]


@router.post("/api/notifications/{notification_id}/read", response_model=NotificationRead)
def mark_notification_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationRead:
    """标记通知为已读"""
    record = NotificationService().mark_read(db, notification_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if record.project_id is not None:
        require_project_access(record.project_id, db, user)
    db.commit()
    return NotificationRead.model_validate(record)


@router.post("/api/notifications/read-all")
def mark_all_notifications_read(
    project_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """标记所有通知为已读"""
    if project_id is not None:
        require_project_access(project_id, db, user)
        count = NotificationService().mark_all_read(db, project_id=project_id)
    else:
        count = NotificationService().mark_all_read(db, project_ids=accessible_project_ids(db, user))
    db.commit()
    return {"marked_read": count}
