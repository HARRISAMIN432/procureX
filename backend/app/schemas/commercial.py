from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    plan_code: str
    status: str
    billing_mode: str
    seat_limit: int
    storage_limit_bytes: int
    ai_run_limit_monthly: int
    entitlements: dict[str, Any]
    current_period_end: datetime | None


class CommercialOverview(BaseModel):
    subscription: SubscriptionRead
    active_members: int
    stored_bytes: int
    open_support_cases: int
    seat_usage_percent: float
    storage_usage_percent: float


class SupportCaseCreate(BaseModel):
    subject: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=10, max_length=10_000)
    priority: Literal["low", "normal", "high", "urgent"] = "normal"


class SupportCaseUpdate(BaseModel):
    status: Literal["open", "in_progress", "waiting_on_customer", "resolved", "closed"]
    resolution: str | None = Field(default=None, max_length=10_000)


class SupportCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    case_number: str
    subject: str
    description: str
    priority: str
    status: str
    resolution: str | None
    created_at: datetime
    updated_at: datetime


class ClosureCreate(BaseModel):
    reason: str = Field(min_length=10, max_length=2_000)
    confirmation: Literal["CLOSE MY WORKSPACE"]


class ClosureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    status: str
    reason: str
    scheduled_for: datetime
    cancelled_at: datetime | None
    created_at: datetime


class AfterSalesCaseCreate(BaseModel):
    purchase_order_id: UUID
    case_type: Literal["return", "replacement", "dispute", "credit_request"]
    description: str = Field(min_length=10, max_length=10_000)
    financial_impact: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=4)


class AfterSalesCaseUpdate(BaseModel):
    status: Literal["open", "investigating", "supplier_action", "resolved", "rejected", "closed"]
    resolution: str | None = Field(default=None, max_length=10_000)


class AfterSalesCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    purchase_order_id: UUID
    case_number: str
    case_type: str
    status: str
    description: str
    resolution: str | None
    financial_impact: Decimal
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ExportRead(BaseModel):
    export_id: UUID
    generated_at: datetime
    organization_id: UUID
    manifest: dict[str, int]
    data: dict[str, list[dict[str, Any]]]
