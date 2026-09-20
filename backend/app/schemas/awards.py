from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.awards import AllocationStatus, AwardDecisionValue, AwardStatus


class MinimumQuantity(BaseModel):
    submission_id: UUID
    rfq_item_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


class AllocationScenarioCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    expected_evaluation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    budget_amount: Decimal | None = Field(default=None, gt=0, max_digits=20, decimal_places=4)
    maximum_suppliers: int | None = Field(default=None, gt=0, le=500)
    allow_split_awards: bool = True
    timeout_seconds: float = Field(default=30, gt=0, le=30)
    fixed_supplier_costs: dict[UUID, Decimal] = Field(default_factory=dict)
    minimum_quantities: list[MinimumQuantity] = Field(default_factory=list, max_length=5000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def unique_minimums_and_nonnegative_costs(self) -> "AllocationScenarioCreate":
        keys = [(item.submission_id, item.rfq_item_id) for item in self.minimum_quantities]
        if len(keys) != len(set(keys)):
            raise ValueError("Minimum quantity overrides must be unique per submission and item")
        if any(value < 0 for value in self.fixed_supplier_costs.values()):
            raise ValueError("Fixed supplier costs cannot be negative")
        return self


class AllocationLineRead(BaseModel):
    submission_id: UUID
    supplier_id: UUID
    rfq_item_id: UUID
    quantity: Decimal
    unit_cost: Decimal
    extended_cost: Decimal


class AllocationScenarioRead(BaseModel):
    id: UUID
    evaluation_id: UUID
    version: int
    name: str
    status: AllocationStatus
    currency: str
    source_evaluation_digest: str
    content_digest: str
    objective_amount: Decimal | None
    best_bound_amount: Decimal | None
    relative_gap: Decimal | None
    runtime_ms: int
    independently_validated: bool
    constraints: dict[str, object]
    constraint_checks: dict[str, bool]
    infeasibility_reasons: list[str]
    allocations: list[AllocationLineRead]
    created_at: datetime


class AllocationScenarioList(BaseModel):
    items: list[AllocationScenarioRead]
    total: int


class AwardCreate(BaseModel):
    expected_scenario_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    recommendation: str = Field(min_length=10, max_length=10_000)
    approval_policy_id: UUID
    analysis_run_id: UUID | None = None

    @field_validator("recommendation")
    @classmethod
    def normalize_recommendation(cls, value: str) -> str:
        return value.strip()


class AwardSubmit(BaseModel):
    expected_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class AwardDecisionWrite(BaseModel):
    expected_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    comment: str | None = Field(default=None, max_length=5000)


class AwardDecisionRead(BaseModel):
    approver_user_id: UUID
    decision: AwardDecisionValue
    comment: str | None
    decided_at: datetime


class AwardRead(BaseModel):
    id: UUID
    rfq_id: UUID
    evaluation_id: UUID
    allocation_scenario_id: UUID
    version: int
    status: AwardStatus
    currency: str
    total_amount: Decimal
    recommendation: str
    dossier: dict[str, object]
    snapshot: dict[str, object]
    content_digest: str
    required_approvals: int
    approval_count: int
    prohibit_self_approval: bool
    decisions: list[AwardDecisionRead]
    created_at: datetime
    submitted_at: datetime | None
    completed_at: datetime | None
