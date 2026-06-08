from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: str | None = None
    is_sensitive: bool = False
    approval_enabled: bool = True
    owner_user_id: int | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    is_sensitive: bool | None = None
    status: str | None = None
    approval_enabled: bool | None = None
    owner_user_id: int | None = None


class ProjectRead(BaseModel):
    id: int
    name: str
    description: str | None
    is_sensitive: bool
    status: str
    approval_enabled: bool
    owner_user_id: int | None

    model_config = {"from_attributes": True}


class ProjectMemberCreate(BaseModel):
    user_id: int
    project_role: str = "member"
    can_read: bool = True
    can_write: bool = True
    can_review: bool = False
    can_manage: bool = False


class ProjectMemberUpdate(BaseModel):
    project_role: str | None = None
    can_read: bool | None = None
    can_write: bool | None = None
    can_review: bool | None = None
    can_manage: bool | None = None


class ProjectMemberRead(BaseModel):
    id: int
    project_id: int
    user_id: int
    project_role: str
    can_read: bool
    can_write: bool
    can_review: bool
    can_manage: bool

    model_config = {"from_attributes": True}


class ProjectReviewerCreate(BaseModel):
    user_id: int
    review_scope: str = "all"


class ProjectReviewerRead(BaseModel):
    id: int
    project_id: int
    user_id: int
    review_scope: str

    model_config = {"from_attributes": True}
