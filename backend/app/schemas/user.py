from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    email: EmailStr | None = None
    role: str = "member"


class UserUpdate(BaseModel):
    display_name: str | None = None
    email: EmailStr | None = None
    role: str | None = None
    status: str | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserPasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserRead(BaseModel):
    id: int
    username: str
    display_name: str
    email: str | None
    role: str
    status: str

    model_config = {"from_attributes": True}
