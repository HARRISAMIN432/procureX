from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.approvals import (
    ApprovalDecisionValue,
    ApprovalPolicyStatus,
    ApprovalRequestStatus,
    BudgetStatus,
)


class BudgetCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]*$", max_length=80)
    name: str = Field(min_length=2, max_length=200)
    currency: str = Field(default="PKR", pattern=r"^[A-Z]{3}$")
    period_start: date
    period_end: date
    initial_allocation: Decimal = Field(ge=0, max_digits=20, decimal_places=4)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name cannot be blank")
        return stripped

    @model_validator(mode="after")
    def valid_period(self) -> "BudgetCreate":
        if self.period_end < self.period_start:
            raise ValueError("period_end must be on or after period_start")
        return self


class BudgetRead(BaseModel):
    id: UUID
    organization_id: UUID
    code: str
    name: str
    currency: str
    period_start: date
    period_end: date
    status: BudgetStatus
    version: int
    available: Decimal
    reserved: Decimal
    committed: Decimal
    consumed: Decimal
    created_at: datetime
    updated_at: datetime


class BudgetList(BaseModel):
    items: list[BudgetRead]
    total: int


class ApprovalPolicyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    minimum_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=4)
    maximum_amount: Decimal | None = Field(default=None, ge=0, max_digits=20, decimal_places=4)
    required_approvals: int = Field(default=1, ge=1, le=20)
    prohibit_self_approval: bool = True
    rules: dict[str, Any] = Field(default_factory=dict)
    effective_from: datetime | None = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Name cannot be blank")
        return stripped

    @field_validator("effective_from")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("effective_from must include a timezone")
        return value

    @model_validator(mode="after")
    def valid_amount_range(self) -> "ApprovalPolicyCreate":
        if self.maximum_amount is not None and self.maximum_amount < self.minimum_amount:
            raise ValueError("maximum_amount must be at least minimum_amount")
        return self


class ApprovalPolicyRead(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    version: int
    status: ApprovalPolicyStatus
    minimum_amount: Decimal
    maximum_amount: Decimal | None
    required_approvals: int
    prohibit_self_approval: bool
    rules: dict[str, Any]
    effective_from: datetime
    effective_to: datetime | None
    created_at: datetime


class ApprovalRequestCreate(BaseModel):
    expected_requisition_version: int = Field(gt=0)
    budget_id: UUID
    policy_id: UUID


class ApprovalDecisionWrite(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class ApprovalDecisionRead(BaseModel):
    id: UUID
    approver_user_id: UUID
    decision: ApprovalDecisionValue
    comment: str | None
    decided_at: datetime


class ApprovalRequestRead(BaseModel):
    id: UUID
    organization_id: UUID
    requisition_id: UUID
    requisition_version: int
    snapshot_digest: str
    budget_id: UUID
    policy_id: UUID
    policy_version: int
    requested_amount: Decimal
    currency: str
    required_approvals: int
    approval_count: int
    prohibit_self_approval: bool
    status: ApprovalRequestStatus
    requested_by_user_id: UUID | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    decisions: list[ApprovalDecisionRead]
