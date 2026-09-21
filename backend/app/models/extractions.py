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


class ExtractionStatus(StrEnum):
    AWAITING_REVIEW = "awaiting_review"
    IN_REVIEW = "in_review"
    COMPLETED = "completed"


class ExtractedFieldStatus(StrEnum):
    PROPOSED = "proposed"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    CONFLICTING = "conflicting"
    VERIFIED = "verified"
    REJECTED = "rejected"


class ReviewAction(StrEnum):
    VERIFY = "verify"
    CORRECT = "correct"
    REJECT = "reject"


class Extraction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "extractions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_version_id", "parse_id"],
            [
                "document_parses.organization_id",
                "document_parses.document_version_id",
                "document_parses.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "analysis_run_id"],
            ["analysis_runs.organization_id", "analysis_runs.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "document_version_id", "version"),
        UniqueConstraint("organization_id", "document_version_id", "result_key"),
        UniqueConstraint("organization_id", "document_version_id", "id"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("revision > 0", name="positive_revision"),
        CheckConstraint("length(content_digest) = 64", name="content_digest_length"),
        CheckConstraint("length(source_digest) = 64", name="source_digest_length"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    parse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    result_key: Mapped[str] = mapped_column(String(200), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[ExtractionStatus] = mapped_column(
        enum_type(ExtractionStatus, "extraction_status"), nullable=False
    )
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ExtractedField(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "extracted_fields"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_version_id", "extraction_id"],
            [
                "extractions.organization_id",
                "extractions.document_version_id",
                "extractions.id",
            ],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "extraction_id", "field_key"),
        UniqueConstraint("organization_id", "extraction_id", "id"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="valid_confidence",
        ),
        CheckConstraint(
            "status <> 'missing' OR (raw_value IS NULL AND normalized_value IS NULL)",
            name="missing_has_no_value",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    extraction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_key: Mapped[str] = mapped_column(String(160), nullable=False)
    label: Mapped[str] = mapped_column(String(250), nullable=False)
    data_type: Mapped[str] = mapped_column(String(50), nullable=False)
    raw_value: Mapped[object | None] = mapped_column(JSONB)
    normalized_value: Mapped[object | None] = mapped_column(JSONB)
    status: Mapped[ExtractedFieldStatus] = mapped_column(
        enum_type(ExtractedFieldStatus, "extracted_field_status"), nullable=False
    )
    is_critical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))


class EvidenceAnchor(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "evidence_anchors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "extraction_id", "field_id"],
            [
                "extracted_fields.organization_id",
                "extracted_fields.extraction_id",
                "extracted_fields.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_version_id", "parse_id", "page_id"],
            [
                "document_pages.organization_id",
                "document_pages.document_version_id",
                "document_pages.parse_id",
                "document_pages.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint(
            "quoted_text IS NOT NULL OR bounding_box IS NOT NULL OR cell_range IS NOT NULL",
            name="has_locator",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    parse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    extraction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    page_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quoted_text: Mapped[str | None] = mapped_column(Text)
    bounding_box: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    cell_range: Mapped[str | None] = mapped_column(String(100))


class FieldReview(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "field_reviews"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "extraction_id", "field_id"],
            [
                "extracted_fields.organization_id",
                "extracted_fields.extraction_id",
                "extracted_fields.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint(
            "previous_status IN "
            "('proposed','missing','ambiguous','conflicting','verified','rejected')",
            name="valid_previous_status",
        ),
        CheckConstraint("reviewed_status IN ('verified','rejected')", name="valid_reviewed_status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    extraction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[ReviewAction] = mapped_column(
        enum_type(ReviewAction, "field_review_action"), nullable=False
    )
    previous_status: Mapped[str] = mapped_column(String(30), nullable=False)
    previous_value: Mapped[object | None] = mapped_column(JSONB)
    reviewed_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reviewed_value: Mapped[object | None] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
