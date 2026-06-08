from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.notification import Notification


class NotificationService:
    def publish(self, db: Session, title: str, message: str = "", project_id: int | None = None) -> Notification:
        record = Notification(
            project_id=project_id,
            title=title,
            message=message,
        )
        db.add(record)
        db.flush()
        return record

    def list_recent(
        self,
        db: Session,
        project_id: int | None = None,
        project_ids: list[int] | None = None,
        include_global: bool = True,
        limit: int = 50,
    ) -> list[Notification]:
        q = db.query(Notification)
        if project_id is not None:
            q = q.filter(Notification.project_id == project_id)
        elif project_ids is not None:
            q = q.filter(Notification.project_id.in_(project_ids) | Notification.project_id.is_(None) if include_global else Notification.project_id.in_(project_ids))
        return q.order_by(Notification.created_at.desc()).limit(limit).all()

    def mark_read(self, db: Session, notification_id: int) -> Notification | None:
        record = db.get(Notification, notification_id)
        if record:
            record.is_read = True
            db.flush()
        return record

    def mark_all_read(self, db: Session, project_id: int | None = None, project_ids: list[int] | None = None) -> int:
        q = db.query(Notification).filter(Notification.is_read.is_(False))
        if project_id is not None:
            q = q.filter(Notification.project_id == project_id)
        elif project_ids is not None:
            q = q.filter(Notification.project_id.in_(project_ids) | Notification.project_id.is_(None))
        count = q.count()
        q.update({"is_read": True})
        db.flush()
        return count
