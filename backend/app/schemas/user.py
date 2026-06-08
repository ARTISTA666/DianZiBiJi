from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    username: str
    password: str
    display_name: str
    email: EmailStr | None = None
    role: str = "member"


class UserUpdate(BaseModel):
    display_name: str | None = None
    email: EmailStr | None = None
    role: str | None = None
    status: str | None = None
    password: str | None = None


class UserRead(BaseModel):
    id: int
    username: str
    display_name: str
    email: str | None
    role: str
    status: str

    model_config = {"from_attributes": True}
