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
    func,
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


class RequisitionStatus(StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    SOURCING = "sourcing"
    ORDERED = "ordered"
    CLOSED = "closed"


class RequirementPriority(StrEnum):
    MANDATORY = "mandatory"
    PREFERRED = "preferred"


class RequirementSource(StrEnum):
    HUMAN = "human"
    AI_ASSISTED = "ai_assisted"


class Requisition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "requisitions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso_code"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    department: Mapped[str | None] = mapped_column(String(150))
    cost_center: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    need_by_date: Mapped[date | None] = mapped_column(Date)
    delivery_location: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[RequisitionStatus] = mapped_column(
        enum_type(RequisitionStatus, "requisition_status"),
        nullable=False,
        default=RequisitionStatus.DRAFT,
        server_default=RequisitionStatus.DRAFT.value,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)


class RequisitionLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "requisition_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "requisition_id"],
            ["requisitions.organization_id", "requisitions.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "requisition_id", "line_number"),
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "requisition_id", "id"),
        CheckConstraint("line_number > 0", name="positive_line_number"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint(
            "estimated_unit_price IS NULL OR estimated_unit_price >= 0",
            name="nonnegative_estimated_unit_price",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requisition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    estimated_unit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    category: Mapped[str | None] = mapped_column(String(120))
    specifications: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    alternatives_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RequisitionRequirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "requisition_requirements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "requisition_id"],
            ["requisitions.organization_id", "requisitions.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "requisition_id", "line_id"],
            [
                "requisition_lines.organization_id",
                "requisition_lines.requisition_id",
                "requisition_lines.id",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requisition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    line_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    priority: Mapped[RequirementPriority] = mapped_column(
        enum_type(RequirementPriority, "requirement_priority"), nullable=False
    )
    criterion: Mapped[str] = mapped_column(Text, nullable=False)
    verification_method: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[RequirementSource] = mapped_column(
        enum_type(RequirementSource, "requirement_source"),
        nullable=False,
        default=RequirementSource.HUMAN,
        server_default=RequirementSource.HUMAN.value,
    )
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class RequisitionRevision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "requisition_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "requisition_id"],
            ["requisitions.organization_id", "requisitions.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "requisition_id", "version"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("length(content_digest) = 64", name="content_digest_length"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requisition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
