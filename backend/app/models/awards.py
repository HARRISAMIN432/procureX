import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class AllocationStatus(StrEnum):
    OPTIMAL = "optimal"
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    UNKNOWN = "unknown"
    INVALID = "invalid"


class AwardStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    STALE = "stale"
    CANCELLED = "cancelled"


class AwardDecisionValue(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class AllocationScenario(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "allocation_scenarios"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "evaluation_id"],
            ["evaluations.organization_id", "evaluations.rfq_id", "evaluations.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "evaluation_id", "version"),
        UniqueConstraint("organization_id", "rfq_id", "id"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("runtime_ms >= 0", name="nonnegative_runtime"),
        CheckConstraint("length(source_evaluation_digest) = 64", name="source_digest_length"),
        CheckConstraint("length(content_digest) = 64", name="content_digest_length"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso_code"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_evaluation_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AllocationStatus] = mapped_column(
        enum_type(AllocationStatus, "allocation_status"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    constraints: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    objective_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    best_bound_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    relative_gap: Mapped[Decimal | None] = mapped_column(Numeric(12, 8))
    runtime_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    independently_validated: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class AllocationLine(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "allocation_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "scenario_id"],
            [
                "allocation_scenarios.organization_id",
                "allocation_scenarios.rfq_id",
                "allocation_scenarios.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "submission_id"],
            [
                "quote_submissions.organization_id",
                "quote_submissions.rfq_id",
                "quote_submissions.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "rfq_item_id"],
            ["rfq_items.organization_id", "rfq_items.rfq_id", "rfq_items.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "scenario_id", "submission_id", "rfq_item_id"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("unit_cost >= 0", name="nonnegative_unit_cost"),
        CheckConstraint("extended_cost >= 0", name="nonnegative_extended_cost"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    scenario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    extended_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)


class Award(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "awards"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "evaluation_id"],
            ["evaluations.organization_id", "evaluations.rfq_id", "evaluations.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "allocation_scenario_id"],
            [
                "allocation_scenarios.organization_id",
                "allocation_scenarios.rfq_id",
                "allocation_scenarios.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "rfq_id", "version"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("total_amount >= 0", name="nonnegative_total_amount"),
        CheckConstraint("required_approvals > 0", name="positive_required_approvals"),
        CheckConstraint("approval_count >= 0", name="nonnegative_approval_count"),
        CheckConstraint(
            "approval_count <= required_approvals", name="approval_count_within_required"
        ),
        CheckConstraint("length(content_digest) = 64", name="content_digest_length"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso_code"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    allocation_scenario_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[AwardStatus] = mapped_column(
        enum_type(AwardStatus, "award_status"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    dossier: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    required_approvals: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prohibit_self_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AwardDecision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "award_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "award_id"],
            ["awards.organization_id", "awards.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "award_id", "approver_user_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    award_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    approver_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[AwardDecisionValue] = mapped_column(
        enum_type(AwardDecisionValue, "award_decision_value"), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
