from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.user import User


def write_audit(
    db: Session,
    *,
    actor: User | None,
    action: str,
    project_id: int | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    detail: dict | None = None,
) -> AuditLog:
    log = AuditLog(
        actor_user_id=actor.id if actor else None,
        project_id=project_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail_json=detail or {},
    )
    db.add(log)
    return log

