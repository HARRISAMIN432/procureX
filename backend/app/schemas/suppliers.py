from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.suppliers import CertificateStatus, QualificationStatus, SupplierStatus


class SupplierContactWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    title: str | None = Field(default=None, max_length=150)
    is_primary: bool = False

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Contact name cannot be blank")
        return stripped


class SupplierPayload(BaseModel):
    legal_name: str = Field(min_length=2, max_length=250)
    trading_name: str | None = Field(default=None, max_length=250)
    registration_country: str = Field(pattern=r"^[A-Z]{2}$")
    registration_number: str = Field(min_length=1, max_length=120)
    tax_identifier: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=500)
    categories: list[str] = Field(default_factory=list, max_length=100)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    contacts: list[SupplierContactWrite] = Field(default_factory=list, max_length=100)

    @field_validator("legal_name", "registration_number")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value cannot be blank")
        return stripped

    @field_validator("categories")
    @classmethod
    def normalize_categories(cls, values: list[str]) -> list[str]:
        normalized = sorted({value.strip() for value in values if value.strip()})
        return normalized

    @model_validator(mode="after")
    def unique_contacts(self) -> "SupplierPayload":
        emails = [str(contact.email).lower() for contact in self.contacts]
        if len(set(emails)) != len(emails):
            raise ValueError("Contact emails must be unique")
        if sum(contact.is_primary for contact in self.contacts) > 1:
            raise ValueError("Only one contact can be primary")
        return self


class SupplierCreate(SupplierPayload):
    pass


class SupplierReplace(SupplierPayload):
    expected_version: int = Field(gt=0)


class SupplierStatusChange(BaseModel):
    expected_version: int = Field(gt=0)
    reason: str = Field(min_length=2, max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("Reason must contain at least two characters")
        return stripped


class SupplierContactRead(BaseModel):
    id: UUID
    name: str
    email: str
    phone: str | None
    title: str | None
    is_primary: bool


class QualificationCreate(BaseModel):
    category: str = Field(min_length=1, max_length=120)

    @field_validator("category")
    @classmethod
    def strip_category(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Category cannot be blank")
        return stripped


class QualificationDecision(BaseModel):
    status: QualificationStatus
    valid_from: date | None = None
    valid_to: date | None = None
    assessment_notes: str = Field(min_length=2, max_length=5000)

    @field_validator("assessment_notes")
    @classmethod
    def strip_assessment_notes(cls, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 2:
            raise ValueError("Assessment notes must contain at least two characters")
        return stripped

    @model_validator(mode="after")
    def validate_decision(self) -> "QualificationDecision":
        if self.status not in {
            QualificationStatus.QUALIFIED,
            QualificationStatus.UNQUALIFIED,
        }:
            raise ValueError("Decision status must be qualified or unqualified")
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to must be on or after valid_from")
        if self.status is QualificationStatus.QUALIFIED and self.valid_to is None:
            raise ValueError("Qualified suppliers require valid_to")
        return self


class QualificationRead(BaseModel):
    id: UUID
    category: str
    status: QualificationStatus
    valid_from: date | None
    valid_to: date | None
    assessment_notes: str | None
    assessed_by_user_id: UUID | None
    assessed_at: datetime | None


class CertificateCreate(BaseModel):
    qualification_id: UUID | None = None
    certificate_type: str = Field(min_length=1, max_length=120)
    certificate_number: str = Field(min_length=1, max_length=150)
    issuer: str = Field(min_length=1, max_length=250)
    issued_on: date | None = None
    expires_on: date | None = None
    document_version_id: UUID | None = None

    @field_validator("certificate_type", "certificate_number", "issuer")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Certificate fields cannot be blank")
        return stripped

    @model_validator(mode="after")
    def validate_dates(self) -> "CertificateCreate":
        if self.issued_on and self.expires_on and self.expires_on < self.issued_on:
            raise ValueError("expires_on must be on or after issued_on")
        return self


class CertificateReview(BaseModel):
    status: CertificateStatus

    @model_validator(mode="after")
    def validate_review(self) -> "CertificateReview":
        if self.status not in {CertificateStatus.VERIFIED, CertificateStatus.REJECTED}:
            raise ValueError("Review status must be verified or rejected")
        return self


class CertificateRead(BaseModel):
    id: UUID
    qualification_id: UUID | None
    certificate_type: str
    certificate_number: str
    issuer: str
    issued_on: date | None
    expires_on: date | None
    status: CertificateStatus
    document_version_id: UUID | None
    reviewed_by_user_id: UUID | None
    reviewed_at: datetime | None


class SupplierRead(BaseModel):
    id: UUID
    organization_id: UUID
    legal_name: str
    trading_name: str | None
    registration_country: str
    registration_number: str
    tax_identifier: str | None
    website: str | None
    categories: list[str]
    capabilities: dict[str, Any]
    status: SupplierStatus
    version: int
    status_reason: str | None
    created_at: datetime
    updated_at: datetime
    contacts: list[SupplierContactRead]
    qualifications: list[QualificationRead]
    certificates: list[CertificateRead]


class SupplierList(BaseModel):
    items: list[SupplierRead]
    total: int
