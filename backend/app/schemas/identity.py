from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


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
