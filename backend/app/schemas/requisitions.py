from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.requisitions import (
    RequirementPriority,
    RequirementSource,
    RequisitionStatus,
)


class RequisitionLineWrite(BaseModel):
    line_number: int = Field(gt=0)
    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    unit: str = Field(min_length=1, max_length=50)
    estimated_unit_price: Decimal | None = Field(
        default=None, ge=0, max_digits=18, decimal_places=4
    )
    category: str | None = Field(default=None, max_length=120)
    specifications: dict[str, Any] = Field(default_factory=dict)
    alternatives_allowed: bool = False

    @field_validator("description", "unit")
    @classmethod
    def strip_required_line_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value cannot be blank")
        return stripped


class RequisitionRequirementWrite(BaseModel):
    line_number: int | None = Field(default=None, gt=0)
    priority: RequirementPriority
    criterion: str = Field(min_length=1, max_length=2000)
    verification_method: str = Field(min_length=1, max_length=500)
    source: RequirementSource = RequirementSource.HUMAN
    confirmed: bool = True

    @field_validator("criterion", "verification_method")
    @classmethod
    def strip_required_requirement_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value cannot be blank")
        return stripped


class RequisitionPayload(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    justification: str = Field(min_length=2, max_length=5000)
    department: str | None = Field(default=None, max_length=150)
    cost_center: str | None = Field(default=None, max_length=100)
    currency: str = Field(default="PKR", pattern=r"^[A-Z]{3}$")
    need_by_date: date | None = None
    delivery_location: str | None = Field(default=None, max_length=500)
    lines: list[RequisitionLineWrite] = Field(default_factory=list, max_length=500)
    requirements: list[RequisitionRequirementWrite] = Field(default_factory=list, max_length=1000)

    @field_validator("title", "justification")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Value cannot be blank")
        return stripped

    @field_validator("need_by_date")
    @classmethod
    def need_date_is_not_past(cls, value: date | None) -> date | None:
        if value is not None and value < date.today():
            raise ValueError("need_by_date cannot be in the past")
        return value

    @model_validator(mode="after")
    def validate_line_references(self) -> "RequisitionPayload":
        line_numbers = [line.line_number for line in self.lines]
        if len(set(line_numbers)) != len(line_numbers):
            raise ValueError("line_number values must be unique")
        known_lines = set(line_numbers)
        invalid = sorted(
            {
                requirement.line_number
                for requirement in self.requirements
                if requirement.line_number is not None
                and requirement.line_number not in known_lines
            }
        )
        if invalid:
            raise ValueError(f"Requirements reference unknown lines: {invalid}")
        return self


class RequisitionCreate(RequisitionPayload):
    pass


class RequisitionReplace(RequisitionPayload):
    expected_version: int = Field(gt=0)


class RequisitionTransition(BaseModel):
    expected_version: int = Field(gt=0)


class RequisitionCancel(RequisitionTransition):
    reason: str = Field(min_length=2, max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Reason cannot be blank")
        return stripped


class RequisitionLineRead(RequisitionLineWrite):
    model_config = ConfigDict(from_attributes=True)

    id: UUID


class RequisitionRequirementRead(BaseModel):
    id: UUID
    line_id: UUID | None
    line_number: int | None
    priority: RequirementPriority
    criterion: str
    verification_method: str
    source: RequirementSource
    confirmed_by_user_id: UUID | None


class RequisitionRead(BaseModel):
    id: UUID
    organization_id: UUID
    title: str
    justification: str
    department: str | None
    cost_center: str | None
    currency: str
    need_by_date: date | None
    delivery_location: str | None
    status: RequisitionStatus
    version: int
    created_by_user_id: UUID | None
    submitted_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime
    updated_at: datetime
    lines: list[RequisitionLineRead]
    requirements: list[RequisitionRequirementRead]


class RequisitionList(BaseModel):
    items: list[RequisitionRead]
    total: int
