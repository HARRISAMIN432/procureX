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


class RfqStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class InvitationStatus(StrEnum):
    INVITED = "invited"
    ACKNOWLEDGED = "acknowledged"
    SUBMITTED = "submitted"
    NO_BID = "no_bid"
    REVOKED = "revoked"


class SubmissionStatus(StrEnum):
    SUBMITTED = "submitted"
    SUPERSEDED = "superseded"
    WITHDRAWN = "withdrawn"


class ClarificationVisibility(StrEnum):
    SHARED = "shared"
    PRIVATE = "private"


class ClarificationStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"


class Rfq(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rfqs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "requisition_id"],
            ["requisitions.organization_id", "requisitions.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "requisition_id"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("publication_number >= 0", name="nonnegative_publication_number"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso_code"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    requisition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    submission_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    terms: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[RfqStatus] = mapped_column(
        enum_type(RfqStatus, "rfq_status"),
        nullable=False,
        default=RfqStatus.DRAFT,
        server_default=RfqStatus.DRAFT.value,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    publication_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancellation_reason: Mapped[str | None] = mapped_column(Text)


class RfqItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rfq_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "rfq_id"],
            ["rfqs.organization_id", "rfqs.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "requisition_line_id"],
            ["requisition_lines.organization_id", "requisition_lines.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "rfq_id", "line_number"),
        UniqueConstraint("organization_id", "rfq_id", "id"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("line_number > 0", name="positive_line_number"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requisition_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120))
    specifications: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    alternatives_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RfqRequirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rfq_requirements"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "rfq_id"],
            ["rfqs.organization_id", "rfqs.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "item_id"],
            ["rfq_items.organization_id", "rfq_items.rfq_id", "rfq_items.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "requisition_requirement_id"],
            ["requisition_requirements.organization_id", "requisition_requirements.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    item_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    requisition_requirement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    priority: Mapped[str] = mapped_column(String(30), nullable=False)
    criterion: Mapped[str] = mapped_column(Text, nullable=False)
    verification_method: Mapped[str] = mapped_column(String(500), nullable=False)


class RfqRevision(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "rfq_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "rfq_id"],
            ["rfqs.organization_id", "rfqs.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "rfq_id", "publication_number"),
        UniqueConstraint("organization_id", "rfq_id", "id"),
        CheckConstraint("publication_number > 0", name="positive_publication_number"),
        CheckConstraint("length(content_digest) = 64", name="content_digest_length"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    publication_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class RfqInvitation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rfq_invitations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "rfq_id"],
            ["rfqs.organization_id", "rfqs.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "rfq_revision_id"],
            ["rfq_revisions.organization_id", "rfq_revisions.rfq_id", "rfq_revisions.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "rfq_id", "supplier_id"),
        UniqueConstraint("organization_id", "rfq_id", "id"),
        UniqueConstraint("organization_id", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[InvitationStatus] = mapped_column(
        enum_type(InvitationStatus, "rfq_invitation_status"),
        nullable=False,
        default=InvitationStatus.INVITED,
        server_default=InvitationStatus.INVITED.value,
    )
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_reason: Mapped[str | None] = mapped_column(Text)


class QuoteSubmission(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "quote_submissions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "invitation_id"],
            ["rfq_invitations.organization_id", "rfq_invitations.rfq_id", "rfq_invitations.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "rfq_revision_id"],
            ["rfq_revisions.organization_id", "rfq_revisions.rfq_id", "rfq_revisions.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "invitation_id", "version"),
        UniqueConstraint("organization_id", "rfq_id", "id"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso_code"),
        CheckConstraint("length(content_digest) = 64", name="content_digest_length"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invitation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_revision_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    valid_until: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_terms: Mapped[str] = mapped_column(Text, nullable=False)
    payment_terms: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[SubmissionStatus] = mapped_column(
        enum_type(SubmissionStatus, "quote_submission_status"),
        nullable=False,
        default=SubmissionStatus.SUBMITTED,
        server_default=SubmissionStatus.SUBMITTED.value,
    )
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuoteLine(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "quote_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "submission_id"],
            [
                "quote_submissions.organization_id",
                "quote_submissions.rfq_id",
                "quote_submissions.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "rfq_item_id"],
            ["rfq_items.organization_id", "rfq_items.rfq_id", "rfq_items.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "submission_id", "rfq_item_id"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("unit_price >= 0", name="nonnegative_unit_price"),
        CheckConstraint("tax_amount >= 0", name="nonnegative_tax_amount"),
        CheckConstraint("freight_amount >= 0", name="nonnegative_freight_amount"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    freight_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=0)
    is_alternative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(String(500))


class RfqClarification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "rfq_clarifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "rfq_id"],
            ["rfqs.organization_id", "rfqs.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "invitation_id"],
            ["rfq_invitations.organization_id", "rfq_invitations.rfq_id", "rfq_invitations.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invitation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    visibility: Mapped[ClarificationVisibility] = mapped_column(
        enum_type(ClarificationVisibility, "clarification_visibility"), nullable=False
    )
    status: Mapped[ClarificationStatus] = mapped_column(
        enum_type(ClarificationStatus, "clarification_status"),
        nullable=False,
        default=ClarificationStatus.OPEN,
        server_default=ClarificationStatus.OPEN.value,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    asked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    answered_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
