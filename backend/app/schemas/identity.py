from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class OrganizationBootstrapRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    organization_slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=63)
    admin_email: EmailStr
    admin_display_name: str = Field(min_length=1, max_length=200)
    default_currency: str = Field(default="PKR", pattern=r"^[A-Z]{3}$")
    timezone: str = Field(default="Asia/Karachi", min_length=1, max_length=64)

    @field_validator("organization_name", "admin_display_name")
    @classmethod
    def strip_names(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name cannot be blank")
        return stripped


class OrganizationSignupRequest(OrganizationBootstrapRequest):
    """OIDC-backed organization signup; the bearer identity becomes its administrator."""


class RoleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    permission_codes: list[str] = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def strip_role_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("permission_codes")
    @classmethod
    def unique_permissions(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("permission_codes must be unique")
        return value


class RoleRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_system: bool
    permission_codes: list[str]


class MemberInviteCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    role_ids: list[UUID] = Field(min_length=1, max_length=20)

    @field_validator("display_name")
    @classmethod
    def strip_display_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("role_ids")
    @classmethod
    def unique_roles(cls, value: list[UUID]) -> list[UUID]:
        if len(set(value)) != len(value):
            raise ValueError("role_ids must be unique")
        return value


class MembershipUpdate(BaseModel):
    status: str | None = Field(default=None, pattern=r"^(active|suspended|revoked)$")
    role_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=20)

    @model_validator(mode="after")
    def require_change(self) -> "MembershipUpdate":
        if self.status is None and self.role_ids is None:
            raise ValueError("At least one membership change is required")
        if self.role_ids is not None and len(set(self.role_ids)) != len(self.role_ids):
            raise ValueError("role_ids must be unique")
        return self


class MemberRead(BaseModel):
    membership_id: UUID
    user_id: UUID
    email: EmailStr
    display_name: str
    status: str
    role_ids: list[UUID]
    joined_at: datetime | None
    invitation_email_status: str
    invitation_email_attempts: int
    invitation_email_sent_at: datetime | None


class OrganizationBootstrapResponse(BaseModel):
    organization_id: UUID
    user_id: UUID
    membership_id: UUID
    role_id: UUID


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    status: str
    default_currency: str
    timezone: str
    created_at: datetime
    updated_at: datetime


class OrganizationWorkspaceRead(BaseModel):
    organization_id: UUID
    organization_slug: str
    organization_name: str
    organization_status: str
    membership_id: UUID
    membership_status: str
    is_pending_invitation: bool


class MembershipContextRead(BaseModel):
    organization_id: UUID
    user_id: UUID
    membership_id: UUID
    permissions: list[str]


class OrganizationSettingsWrite(BaseModel):
    settings: dict[str, Any]
    effective_from: datetime | None = None

    @field_validator("effective_from")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("effective_from must include a timezone")
        return value


class OrganizationSettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    version: int
    settings: dict[str, Any]
    effective_from: datetime
    effective_to: datetime | None
    created_at: datetime
