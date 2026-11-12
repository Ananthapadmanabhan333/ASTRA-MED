from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ApiModel

RoleKey = Literal["flight_surgeon", "mission_operator", "analyst", "admin"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserInfo(ApiModel):
    id: str
    username: str
    display_name: str
    role: str
    role_label: str
    active: bool = True
    last_login_at: datetime | None = None


class SessionInfo(ApiModel):
    user: UserInfo
    permissions: list[str]
    method: Literal["session", "bearer", "disabled"]
    csrf_token: str | None = Field(
        default=None, description="Send as X-CSRF-Token on every state-changing cookie-authenticated request"
    )
    expires_at: datetime | None = None
    auth_enabled: bool


class TokenResponse(ApiModel):
    access_token: str = Field(description="Bearer token for non-browser API clients. Treat it like a password.")
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
    user: UserInfo


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class RoleInfo(ApiModel):
    key: RoleKey
    label: str
    description: str
    permissions: list[str]


class PermissionInfo(ApiModel):
    key: str
    description: str


class AccessMatrix(ApiModel):
    roles: list[RoleInfo]
    permissions: list[PermissionInfo]


class AdminUser(UserInfo):
    created_at: datetime
    locked_until: datetime | None = None
    failed_logins: int = 0


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    role: RoleKey
    password: str = Field(min_length=1, max_length=256)


class UserUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    role: RoleKey | None = None
    active: bool | None = None
    unlock: bool = False


class AuditEntry(ApiModel):
    id: int
    ts: datetime
    user_id: str | None
    username: str | None
    role: str | None
    action: str
    resource_type: str | None
    resource_id: str | None
    outcome: Literal["success", "denied", "failure"]
    status_code: int | None
    ip: str | None
    request_id: str | None
    detail: dict[str, Any]
