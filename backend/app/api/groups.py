from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.database import get_db
from app.models.group import Group, GroupMember
from app.models.user import User
from app.schemas.group import GroupCreate, GroupMemberCreate, GroupMemberRead, GroupRead, GroupUpdate
from app.services.audit import write_audit

router = APIRouter(prefix="/groups", tags=["groups"])


def _require_user(db: Session, user_id: int | None) -> None:
    if user_id is None:
        return
    if db.get(User, user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


@router.get("", response_model=list[GroupRead])
def list_groups(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[Group]:
    return db.query(Group).order_by(Group.id).all()


@router.post("", response_model=GroupRead)
def create_group(payload: GroupCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> Group:
    _require_user(db, payload.leader_user_id)
    group = Group(name=payload.name, description=payload.description, leader_user_id=payload.leader_user_id)
    db.add(group)
    db.flush()
    write_audit(db, actor=admin, action="create_group", target_type="group", target_id=group.id)
    db.commit()
    db.refresh(group)
    return group


@router.get("/{group_id}", response_model=GroupRead)
def get_group(group_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return group


@router.patch("/{group_id}", response_model=GroupRead)
def update_group(
    group_id: int,
    payload: GroupUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    fields = payload.model_fields_set
    if "name" in fields:
        group.name = payload.name
    if "description" in fields:
        group.description = payload.description
    if "leader_user_id" in fields:
        _require_user(db, payload.leader_user_id)
        group.leader_user_id = payload.leader_user_id
    write_audit(db, actor=admin, action="update_group", target_type="group", target_id=group.id)
    db.commit()
    db.refresh(group)
    return group


@router.get("/{group_id}/members", response_model=list[GroupMemberRead])
def list_group_members(group_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[GroupMember]:
    if db.get(Group, group_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return db.query(GroupMember).filter(GroupMember.group_id == group_id).order_by(GroupMember.id).all()


@router.post("/{group_id}/members", response_model=GroupMemberRead)
def add_group_member(
    group_id: int,
    payload: GroupMemberCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> GroupMember:
    if db.get(Group, group_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    _require_user(db, payload.user_id)
    membership = (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group_id, GroupMember.user_id == payload.user_id)
        .first()
    )
    if membership is None:
        membership = GroupMember(group_id=group_id, user_id=payload.user_id)
        db.add(membership)
    membership.group_role = payload.group_role
    write_audit(db, actor=admin, action="update_group_member", target_type="user", target_id=payload.user_id)
    db.commit()
    db.refresh(membership)
    return membership


@router.delete("/{group_id}/members/{user_id}")
def remove_group_member(
    group_id: int,
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    membership = (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
        .first()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group member not found")
    db.delete(membership)
    write_audit(db, actor=admin, action="update_group_member", target_type="user", target_id=user_id)
    db.commit()
    return {"ok": True}
