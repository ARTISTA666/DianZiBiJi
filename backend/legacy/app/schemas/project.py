from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    is_sensitive: bool = False
    approval_enabled: bool = True
    owner_user_id: int | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
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


class ProjectListResponse(BaseModel):
    items: list[ProjectRead]
    total: int
    skip: int = 0
    limit: int = 20


class ProjectMemberCreate(BaseModel):
    user_id: int
    project_role: str = "member"
    can_read: bool = True
    can_write: bool = True
    can_review: bool = False
    can_evaluate: bool = False
    can_manage: bool = False


class ProjectMemberUpdate(BaseModel):
    project_role: str | None = None
    can_read: bool | None = None
    can_write: bool | None = None
    can_review: bool | None = None
    can_evaluate: bool | None = None
    can_manage: bool | None = None


class ProjectMemberRead(BaseModel):
    id: int
    project_id: int
    user_id: int
    project_role: str
    can_read: bool
    can_write: bool
    can_review: bool
    can_evaluate: bool
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
