from pydantic import BaseModel


class GroupCreate(BaseModel):
    name: str
    description: str | None = None
    leader_user_id: int | None = None


class GroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    leader_user_id: int | None = None


class GroupRead(BaseModel):
    id: int
    name: str
    description: str | None
    leader_user_id: int | None

    model_config = {"from_attributes": True}


class GroupMemberCreate(BaseModel):
    user_id: int
    group_role: str = "member"


class GroupMemberRead(BaseModel):
    id: int
    group_id: int
    user_id: int
    group_role: str

    model_config = {"from_attributes": True}
