from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin, require_project_access, require_project_manager
from app.core.database import get_db
from app.models.project import Project, ProjectMember, ProjectReviewer, ProjectRole, ProjectStatus
from app.models.user import User, UserRole
from app.schemas.project import (
    ProjectCreate,
    ProjectMemberCreate,
    ProjectMemberRead,
    ProjectMemberUpdate,
    ProjectRead,
    ProjectReviewerCreate,
    ProjectReviewerRead,
    ProjectUpdate,
)
from app.services.audit import write_audit

router = APIRouter(prefix="/projects", tags=["projects"])


def _project_member(db: Session, project_id: int, user_id: int) -> ProjectMember | None:
    return (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.user_id == user_id)
        .first()
    )


def _ensure_owner_membership(db: Session, project_id: int, user_id: int | None) -> None:
    if user_id is None:
        return
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Owner user not found")
    membership = _project_member(db, project_id, user_id)
    if membership is None:
        db.add(
            ProjectMember(
                project_id=project_id,
                user_id=user_id,
                project_role=ProjectRole.OWNER,
                can_read=True,
                can_write=True,
                can_review=True,
                can_manage=True,
            )
        )
        return
    membership.project_role = ProjectRole.OWNER
    membership.can_read = True
    membership.can_write = True
    membership.can_review = True
    membership.can_manage = True


def _manager_count(db: Session, project_id: int) -> int:
    return (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project_id, ProjectMember.can_read.is_(True))
        .filter((ProjectMember.can_manage.is_(True)) | (ProjectMember.project_role == ProjectRole.OWNER))
        .count()
    )


def _is_member_manager(membership: ProjectMember) -> bool:
    return bool(membership.can_read and (membership.can_manage or membership.project_role == ProjectRole.OWNER))


def _require_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("", response_model=list[ProjectRead])
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[Project]:
    if user.role == UserRole.SUPER_ADMIN:
        return db.query(Project).order_by(Project.id).all()
    if user.role == UserRole.PI:
        member_project_ids = db.query(ProjectMember.project_id).filter(ProjectMember.user_id == user.id)
        return (
            db.query(Project)
            .filter(or_(Project.is_sensitive.is_(False), Project.id.in_(member_project_ids)))
            .order_by(Project.id)
            .all()
        )
    project_ids = db.query(ProjectMember.project_id).filter(ProjectMember.user_id == user.id, ProjectMember.can_read.is_(True))
    return db.query(Project).filter(Project.id.in_(project_ids)).order_by(Project.id).all()


@router.post("", response_model=ProjectRead)
def create_project(payload: ProjectCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> Project:
    if payload.owner_user_id is not None:
        _require_user(db, payload.owner_user_id)
    project = Project(
        name=payload.name,
        description=payload.description,
        is_sensitive=payload.is_sensitive,
        approval_enabled=payload.approval_enabled,
        owner_user_id=payload.owner_user_id,
    )
    db.add(project)
    db.flush()
    _ensure_owner_membership(db, project.id, payload.owner_user_id)
    write_audit(db, actor=admin, action="create_project", project_id=project.id, target_type="project", target_id=project.id)
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Project:
    return require_project_access(project_id, db, user)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: int,
    payload: ProjectUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    project = require_project_manager(project_id, db, user)
    fields = payload.model_fields_set
    if "name" in fields:
        project.name = payload.name
    if "description" in fields:
        project.description = payload.description
    if payload.is_sensitive is not None:
        project.is_sensitive = payload.is_sensitive
    if payload.status is not None:
        project.status = ProjectStatus(payload.status)
    if payload.approval_enabled is not None:
        project.approval_enabled = payload.approval_enabled
    if "owner_user_id" in fields:
        if payload.owner_user_id is not None:
            _require_user(db, payload.owner_user_id)
        project.owner_user_id = payload.owner_user_id
        _ensure_owner_membership(db, project.id, payload.owner_user_id)
    write_audit(db, actor=user, action="update_project", project_id=project.id, target_type="project", target_id=project.id)
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/members")
def add_project_member(
    project_id: int,
    payload: ProjectMemberCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    require_project_manager(project_id, db, user)
    _require_user(db, payload.user_id)
    membership = _project_member(db, project_id, payload.user_id)
    if membership is None:
        membership = ProjectMember(project_id=project_id, user_id=payload.user_id)
        db.add(membership)
    membership.project_role = ProjectRole(payload.project_role)
    membership.can_read = payload.can_read
    membership.can_write = payload.can_write
    membership.can_review = payload.can_review
    membership.can_manage = payload.can_manage
    write_audit(
        db,
        actor=user,
        action="update_project_member",
        project_id=project_id,
        target_type="user",
        target_id=payload.user_id,
    )
    db.commit()
    return {"ok": True}


@router.get("/{project_id}/members", response_model=list[ProjectMemberRead])
def list_project_members(
    project_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ProjectMember]:
    require_project_access(project_id, db, user)
    return db.query(ProjectMember).filter(ProjectMember.project_id == project_id).order_by(ProjectMember.id).all()


@router.patch("/{project_id}/members/{user_id}", response_model=ProjectMemberRead)
def update_project_member(
    project_id: int,
    user_id: int,
    payload: ProjectMemberUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectMember:
    require_project_manager(project_id, db, user)
    membership = _project_member(db, project_id, user_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project member not found")
    was_manager = _is_member_manager(membership)
    next_role = ProjectRole(payload.project_role) if payload.project_role is not None else membership.project_role
    next_can_read = payload.can_read if payload.can_read is not None else membership.can_read
    next_can_manage = payload.can_manage if payload.can_manage is not None else membership.can_manage
    next_is_manager = bool(next_can_read and (next_can_manage or next_role == ProjectRole.OWNER))
    if was_manager and not next_is_manager and _manager_count(db, project_id) <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project must keep at least one manager")
    if user_id == user.id and user.role != UserRole.SUPER_ADMIN and not next_is_manager:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot remove your own project manage access")
    if payload.project_role is not None:
        membership.project_role = next_role
    if payload.can_read is not None:
        membership.can_read = payload.can_read
    if payload.can_write is not None:
        membership.can_write = payload.can_write
    if payload.can_review is not None:
        membership.can_review = payload.can_review
    if payload.can_manage is not None:
        membership.can_manage = payload.can_manage
    write_audit(db, actor=user, action="update_project_member", project_id=project_id, target_type="user", target_id=user_id)
    db.commit()
    db.refresh(membership)
    return membership


@router.delete("/{project_id}/members/{user_id}")
def remove_project_member(
    project_id: int,
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    require_project_manager(project_id, db, user)
    membership = _project_member(db, project_id, user_id)
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project member not found")
    if _is_member_manager(membership) and _manager_count(db, project_id) <= 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Project must keep at least one manager")
    if user_id == user.id and user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot remove yourself from project managers")
    db.delete(membership)
    write_audit(db, actor=user, action="change_permission", project_id=project_id, target_type="user", target_id=user_id)
    db.commit()
    return {"ok": True}


@router.post("/{project_id}/reviewers", response_model=ProjectReviewerRead)
def add_project_reviewer(
    project_id: int,
    payload: ProjectReviewerCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProjectReviewer:
    require_project_manager(project_id, db, user)
    _require_user(db, payload.user_id)
    reviewer = (
        db.query(ProjectReviewer)
        .filter(ProjectReviewer.project_id == project_id, ProjectReviewer.user_id == payload.user_id)
        .first()
    )
    if reviewer is None:
        reviewer = ProjectReviewer(project_id=project_id, user_id=payload.user_id)
        db.add(reviewer)
    reviewer.review_scope = payload.review_scope
    membership = _project_member(db, project_id, payload.user_id)
    if membership is None:
        db.add(
            ProjectMember(
                project_id=project_id,
                user_id=payload.user_id,
                project_role=ProjectRole.REVIEWER,
                can_read=True,
                can_write=False,
                can_review=True,
                can_manage=False,
            )
        )
    else:
        membership.can_review = True
        membership.project_role = ProjectRole.REVIEWER
    write_audit(db, actor=user, action="change_permission", project_id=project_id, target_type="user", target_id=payload.user_id)
    db.commit()
    db.refresh(reviewer)
    return reviewer


@router.delete("/{project_id}/reviewers/{user_id}")
def remove_project_reviewer(
    project_id: int,
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    require_project_manager(project_id, db, user)
    reviewer = (
        db.query(ProjectReviewer)
        .filter(ProjectReviewer.project_id == project_id, ProjectReviewer.user_id == user_id)
        .first()
    )
    if reviewer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project reviewer not found")
    db.delete(reviewer)
    membership = _project_member(db, project_id, user_id)
    if membership is not None:
        membership.can_review = False
    write_audit(db, actor=user, action="change_permission", project_id=project_id, target_type="user", target_id=user_id)
    db.commit()
    return {"ok": True}
