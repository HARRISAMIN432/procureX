import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


def enum_type(enum: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=30,
        values_callable=lambda enum_class: [member.value for member in enum_class],
    )


class BudgetStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class BudgetEntryType(StrEnum):
    ALLOCATION = "allocation"
    ADJUSTMENT = "adjustment"
    RESERVATION = "reservation"
    RELEASE = "release"
    COMMITMENT = "commitment"
    CONSUMPTION = "consumption"


class ReservationStatus(StrEnum):
    ACTIVE = "active"
    RELEASED = "released"
    COMMITTED = "committed"


class ApprovalPolicyStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ApprovalRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    STALE = "stale"


class ApprovalDecisionValue(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class Budget(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("organization_id", "code"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso_code"),
        CheckConstraint("period_end >= period_start", name="valid_period"),
        CheckConstraint("version > 0", name="positive_version"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[BudgetStatus] = mapped_column(
        enum_type(BudgetStatus, "budget_status"),
        nullable=False,
        default=BudgetStatus.ACTIVE,
        server_default=BudgetStatus.ACTIVE.value,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class BudgetLedgerEntry(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "budget_ledger_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "budget_id"],
            ["budgets.organization_id", "budgets.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "requisition_id"],
            ["requisitions.organization_id", "requisitions.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "idempotency_key"),
        CheckConstraint(
            "delta_available <> 0 OR delta_reserved <> 0 OR delta_committed <> 0 "
            "OR delta_consumed <> 0",
            name="nonzero_delta",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    budget_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requisition_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    entry_type: Mapped[BudgetEntryType] = mapped_column(
        enum_type(BudgetEntryType, "budget_entry_type"), nullable=False
    )
    delta_available: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    delta_reserved: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    delta_committed: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    delta_consumed: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(100), nullable=False)
    reference_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApprovalPolicy(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "approval_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", "version"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("required_approvals > 0", name="positive_required_approvals"),
        CheckConstraint("minimum_amount >= 0", name="nonnegative_minimum_amount"),
        CheckConstraint(
            "maximum_amount IS NULL OR maximum_amount >= minimum_amount",
            name="valid_amount_range",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from", name="valid_effective_range"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ApprovalPolicyStatus] = mapped_column(
        enum_type(ApprovalPolicyStatus, "approval_policy_status"),
        nullable=False,
        default=ApprovalPolicyStatus.ACTIVE,
        server_default=ApprovalPolicyStatus.ACTIVE.value,
    )
    minimum_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    maximum_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    required_approvals: Mapped[int] = mapped_column(Integer, nullable=False)
    prohibit_self_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rules: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class ApprovalRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "requisition_id"],
            ["requisitions.organization_id", "requisitions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "budget_id"],
            ["budgets.organization_id", "budgets.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "policy_id"],
            ["approval_policies.organization_id", "approval_policies.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "requisition_id", "requisition_version"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("requisition_version > 0", name="positive_requisition_version"),
        CheckConstraint("requested_amount > 0", name="positive_requested_amount"),
        CheckConstraint("required_approvals > 0", name="positive_required_approvals"),
        CheckConstraint("approval_count >= 0", name="nonnegative_approval_count"),
        CheckConstraint(
            "approval_count <= required_approvals", name="approval_count_within_required"
        ),
        CheckConstraint("policy_version > 0", name="positive_policy_version"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso_code"),
        CheckConstraint("length(snapshot_digest) = 64", name="snapshot_digest_length"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requisition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requisition_version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    budget_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    required_approvals: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prohibit_self_approval: Mapped[bool] = mapped_column(Boolean, nullable=False)
    policy_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    status: Mapped[ApprovalRequestStatus] = mapped_column(
        enum_type(ApprovalRequestStatus, "approval_request_status"),
        nullable=False,
        default=ApprovalRequestStatus.PENDING,
        server_default=ApprovalRequestStatus.PENDING.value,
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApprovalDecision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "approval_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "approval_request_id"],
            ["approval_requests.organization_id", "approval_requests.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "approval_request_id", "approver_user_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approval_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approver_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[ApprovalDecisionValue] = mapped_column(
        enum_type(ApprovalDecisionValue, "approval_decision_value"), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BudgetReservation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "budget_reservations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "budget_id"],
            ["budgets.organization_id", "budgets.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "requisition_id"],
            ["requisitions.organization_id", "requisitions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "approval_request_id"],
            ["approval_requests.organization_id", "approval_requests.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "approval_request_id"),
        CheckConstraint("amount > 0", name="positive_amount"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    budget_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requisition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approval_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        enum_type(ReservationStatus, "budget_reservation_status"),
        nullable=False,
        default=ReservationStatus.ACTIVE,
        server_default=ReservationStatus.ACTIVE.value,
    )
