from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.note import ExperimentNote
from app.models.project import Project, ProjectMember, ProjectReviewer, ProjectRole
from app.models.user import User, UserRole, UserStatus


bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.get(User, int(user_id))
    if user is None or user.status != UserStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin permission required")
    return user


def can_access_project(db: Session, user: User, project: Project) -> bool:
    if user.role == UserRole.SUPER_ADMIN:
        return True
    if project.owner_user_id == user.id:
        return True
    if user.role == UserRole.PI and not project.is_sensitive:
        return True
    membership = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project.id, ProjectMember.user_id == user.id, ProjectMember.can_read.is_(True))
        .first()
    )
    return membership is not None


def require_project_access(project_id: int, db: Session, user: User) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if not can_access_project(db, user, project):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Project access denied")
    return project


def require_note_access(note_id: int, db: Session, user: User) -> ExperimentNote:
    note = db.get(ExperimentNote, note_id)
    if note is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    require_project_access(note.project_id, db, user)
    return note


def accessible_project_ids(db: Session, user: User) -> list[int]:
    if user.role == UserRole.SUPER_ADMIN:
        return [project_id for (project_id,) in db.query(Project.id).all()]

    project_ids = {project_id for (project_id,) in db.query(Project.id).filter(Project.owner_user_id == user.id).all()}
    project_ids.update(
        project_id
        for (project_id,) in db.query(ProjectMember.project_id)
        .filter(ProjectMember.user_id == user.id, ProjectMember.can_read.is_(True))
        .all()
    )
    if user.role == UserRole.PI:
        project_ids.update(project_id for (project_id,) in db.query(Project.id).filter(Project.is_sensitive.is_(False)).all())
    return sorted(project_ids)


def _project_membership(db: Session, user: User, project_id: int) -> ProjectMember | None:
    return (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user.id)
        .first()
    )


def can_write_project(db: Session, user: User, project_id: int) -> bool:
    if user.role == UserRole.SUPER_ADMIN:
        return True
    membership = _project_membership(db, user, project_id)
    return bool(membership and membership.can_write)


def can_manage_project(db: Session, user: User, project_id: int) -> bool:
    if user.role == UserRole.SUPER_ADMIN:
        return True
    project = db.get(Project, project_id)
    if project is None:
        return False
    if project.owner_user_id == user.id:
        return True
    membership = _project_membership(db, user, project_id)
    return bool(membership and (membership.can_manage or membership.project_role == ProjectRole.OWNER))


def require_project_manager(project_id: int, db: Session, user: User) -> Project:
    project = require_project_access(project_id, db, user)
    if not can_manage_project(db, user, project_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Project manage permission required")
    return project


def can_review_project(db: Session, user: User, project_id: int) -> bool:
    if user.role == UserRole.SUPER_ADMIN:
        return True
    membership = _project_membership(db, user, project_id)
    if membership and (membership.can_review or membership.can_manage):
        return True
    reviewer = (
        db.query(ProjectReviewer)
        .filter(ProjectReviewer.project_id == project_id, ProjectReviewer.user_id == user.id)
        .first()
    )
    return reviewer is not None
