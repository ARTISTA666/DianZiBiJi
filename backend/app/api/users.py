from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.auth import set_auth_cookie
from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserRole, UserStatus
from app.schemas.auth import TokenResponse
from app.schemas.user import UserCreate, UserPasswordChange, UserRead, UserUpdate
from app.services.audit import write_audit

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserRead])
def list_users(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[User]:
    return db.query(User).order_by(User.id).all()


@router.post("", response_model=UserRead)
def create_user(payload: UserCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> User:
    if db.query(User).filter(User.username == payload.username).first() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        email=payload.email,
        role=UserRole(payload.role),
    )
    db.add(user)
    db.flush()
    write_audit(db, actor=admin, action="create_user", target_type="user", target_id=user.id)
    db.commit()
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    fields = payload.model_fields_set
    if "display_name" in fields:
        user.display_name = payload.display_name
    if "email" in fields:
        user.email = payload.email
    if payload.role is not None:
        user.role = UserRole(payload.role)
    if payload.status is not None:
        user.status = UserStatus(payload.status)
    if payload.password:
        user.password_hash = hash_password(payload.password)
        user.auth_version += 1
    write_audit(db, actor=admin, action="update_user", target_type="user", target_id=user.id)
    db.commit()
    db.refresh(user)
    return user


@router.post("/me/password", response_model=TokenResponse)
def change_own_password(
    payload: UserPasswordChange,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TokenResponse:
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    current_user.password_hash = hash_password(payload.new_password)
    current_user.auth_version += 1
    write_audit(db, actor=current_user, action="change_password", target_type="user", target_id=current_user.id)
    db.commit()
    token = create_access_token(str(current_user.id), current_user.auth_version)
    # Refresh the auth cookie so browser sessions survive the auth_version bump.
    set_auth_cookie(response, token)
    return TokenResponse(access_token=token)


@router.post("/{user_id}/disable", response_model=UserRead)
def disable_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot disable current admin")
    user.status = UserStatus.DISABLED
    user.auth_version += 1
    write_audit(db, actor=admin, action="update_user", target_type="user", target_id=user.id)
    db.commit()
    db.refresh(user)
    return user
