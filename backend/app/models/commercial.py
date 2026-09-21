import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    PAST_DUE = "past_due"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class OrganizationSubscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_subscriptions"
    __table_args__ = (
        UniqueConstraint("organization_id"),
        CheckConstraint("seat_limit > 0", name="positive_seat_limit"),
        CheckConstraint("storage_limit_bytes > 0", name="positive_storage_limit"),
        CheckConstraint("ai_run_limit_monthly >= 0", name="nonnegative_ai_run_limit"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    plan_code: Mapped[str] = mapped_column(String(50), nullable=False, default="community")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    billing_mode: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")
    seat_limit: Mapped[int] = mapped_column(nullable=False, default=5)
    storage_limit_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=536_870_912
    )
    ai_run_limit_monthly: Mapped[int] = mapped_column(nullable=False, default=25)
    entitlements: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DataExportRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "data_export_requests"
    __table_args__ = (UniqueConstraint("organization_id", "id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="completed")
    format: Mapped[str] = mapped_column(String(20), nullable=False, default="json")
    manifest: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrganizationClosureRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_closure_requests"
    __table_args__ = (UniqueConstraint("organization_id", "id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="scheduled")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupportCase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "support_cases"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "case_number"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    case_number: Mapped[str] = mapped_column(String(40), nullable=False)
    requester_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AfterSalesCase(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "after_sales_cases"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "case_number"),
        CheckConstraint("financial_impact >= 0", name="nonnegative_financial_impact"),
        ForeignKeyConstraint(
            ["organization_id", "purchase_order_id"],
            ["purchase_orders.organization_id", "purchase_orders.id"],
            ondelete="RESTRICT",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    case_number: Mapped[str] = mapped_column(String(40), nullable=False)
    case_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    resolution: Mapped[str | None] = mapped_column(Text)
    financial_impact: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
