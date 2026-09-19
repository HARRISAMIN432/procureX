from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.sourcing import (
    ClarificationStatus,
    ClarificationVisibility,
    InvitationStatus,
    RfqStatus,
    SubmissionStatus,
)


def required_text(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("Value cannot be blank")
    return stripped


class RfqCreate(BaseModel):
    requisition_id: UUID
    title: str = Field(min_length=2, max_length=300)
    submission_deadline: datetime
    terms: dict[str, Any] = Field(default_factory=dict)

    _title = field_validator("title")(required_text)

    @field_validator("submission_deadline")
    @classmethod
    def deadline_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("submission_deadline must include a timezone")
        return value


class RfqReplace(BaseModel):
    expected_version: int = Field(gt=0)
    title: str = Field(min_length=2, max_length=300)
    submission_deadline: datetime
    terms: dict[str, Any] = Field(default_factory=dict)

    _title = field_validator("title")(required_text)

    @field_validator("submission_deadline")
    @classmethod
    def deadline_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("submission_deadline must include a timezone")
        return value


class RfqTransition(BaseModel):
    expected_version: int = Field(gt=0)


class RfqAmend(RfqTransition):
    submission_deadline: datetime
    terms: dict[str, Any]
    reason: str = Field(min_length=2, max_length=2000)

    _reason = field_validator("reason")(required_text)

    @field_validator("submission_deadline")
    @classmethod
    def deadline_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("submission_deadline must include a timezone")
        return value


class RfqCancel(RfqTransition):
    reason: str = Field(min_length=2, max_length=2000)

    _reason = field_validator("reason")(required_text)


class InvitationCreate(BaseModel):
    supplier_ids: list[UUID] = Field(min_length=1, max_length=100)

    @field_validator("supplier_ids")
    @classmethod
    def unique_supplier_ids(cls, values: list[UUID]) -> list[UUID]:
        if len(values) != len(set(values)):
            raise ValueError("supplier_ids must be unique")
        return values


class RfqItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    requisition_line_id: UUID
    line_number: int
    description: str
    quantity: Decimal
    unit: str
    category: str | None
    specifications: dict[str, Any]
    alternatives_allowed: bool


class RfqRequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    item_id: UUID | None
    priority: str
    criterion: str
    verification_method: str


class InvitationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    supplier_id: UUID
    rfq_revision_id: UUID | None
    status: InvitationStatus
    invited_at: datetime | None
    responded_at: datetime | None


class SubmissionLineWrite(BaseModel):
    rfq_item_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    freight_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    is_alternative: bool = False
    description: str | None = Field(default=None, max_length=500)


class SubmissionCreate(BaseModel):
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    valid_until: date
    delivery_terms: str = Field(min_length=2, max_length=5000)
    payment_terms: str | None = Field(default=None, max_length=5000)
    notes: str | None = Field(default=None, max_length=10000)
    lines: list[SubmissionLineWrite] = Field(min_length=1, max_length=500)

    _delivery_terms = field_validator("delivery_terms")(required_text)

    @model_validator(mode="after")
    def unique_items(self) -> "SubmissionCreate":
        item_ids = [line.rfq_item_id for line in self.lines]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("Each RFQ item may appear only once")
        return self


class SubmissionWithdraw(BaseModel):
    expected_rfq_version: int = Field(gt=0)
    reason: str = Field(min_length=2, max_length=2000)

    _reason = field_validator("reason")(required_text)


class SubmissionLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    rfq_item_id: UUID
    quantity: Decimal
    unit_price: Decimal
    tax_amount: Decimal
    freight_amount: Decimal
    is_alternative: bool
    description: str | None


class SubmissionRead(BaseModel):
    id: UUID
    invitation_id: UUID
    supplier_id: UUID
    rfq_revision_id: UUID
    version: int
    currency: str
    valid_until: date
    delivery_terms: str
    payment_terms: str | None
    notes: str | None
    status: SubmissionStatus
    content_digest: str
    submitted_at: datetime
    withdrawn_at: datetime | None
    lines: list[SubmissionLineRead]


class ClarificationCreate(BaseModel):
    invitation_id: UUID | None = None
    visibility: ClarificationVisibility
    question: str = Field(min_length=2, max_length=5000)

    _question = field_validator("question")(required_text)

    @model_validator(mode="after")
    def private_requires_invitation(self) -> "ClarificationCreate":
        if self.visibility is ClarificationVisibility.PRIVATE and self.invitation_id is None:
            raise ValueError("Private clarifications require invitation_id")
        return self


class ClarificationAnswer(BaseModel):
    answer: str = Field(min_length=2, max_length=10000)

    _answer = field_validator("answer")(required_text)


class ClarificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invitation_id: UUID | None
    visibility: ClarificationVisibility
    status: ClarificationStatus
    question: str
    answer: str | None
    asked_by_user_id: UUID | None
    answered_by_user_id: UUID | None
    answered_at: datetime | None
    created_at: datetime


class RfqRead(BaseModel):
    id: UUID
    organization_id: UUID
    requisition_id: UUID
    title: str
    currency: str
    submission_deadline: datetime
    terms: dict[str, Any]
    status: RfqStatus
    version: int
    publication_number: int
    published_at: datetime | None
    closed_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime
    items: list[RfqItemRead]
    requirements: list[RfqRequirementRead]
    invitations: list[InvitationRead]
    submissions: list[SubmissionRead]
    clarifications: list[ClarificationRead]


class RfqList(BaseModel):
    items: list[RfqRead]
    total: int
