import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
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


class EvaluationStatus(StrEnum):
    COMPLETED = "completed"


class RequirementOutcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class OfferEligibility(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    BLOCKED = "blocked"


class Evaluation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "rfq_id"],
            ["rfqs.organization_id", "rfqs.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "rfq_id", "version"),
        UniqueConstraint("organization_id", "rfq_id", "id"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("source_rfq_version > 0", name="positive_source_rfq_version"),
        CheckConstraint("publication_number > 0", name="positive_publication_number"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso_code"),
        CheckConstraint("length(content_digest) = 64", name="content_digest_length"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_rfq_version: Mapped[int] = mapped_column(Integer, nullable=False)
    publication_number: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[EvaluationStatus] = mapped_column(
        enum_type(EvaluationStatus, "evaluation_status"), nullable=False
    )
    scoring_policy: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class OfferEvaluation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "offer_evaluations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "evaluation_id"],
            ["evaluations.organization_id", "evaluations.rfq_id", "evaluations.id"],
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
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "evaluation_id", "submission_id"),
        UniqueConstraint("organization_id", "rfq_id", "evaluation_id", "id"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("landed_cost >= 0", name="nonnegative_landed_cost"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="valid_score"),
        CheckConstraint(
            "preferred_ratio >= 0 AND preferred_ratio <= 1", name="valid_preferred_ratio"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    submission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    eligibility: Mapped[OfferEligibility] = mapped_column(
        enum_type(OfferEligibility, "offer_eligibility"), nullable=False
    )
    landed_cost: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    preferred_ratio: Mapped[Decimal] = mapped_column(Numeric(7, 6), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(7, 4))


class RequirementCheck(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "requirement_checks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "evaluation_id", "offer_evaluation_id"],
            [
                "offer_evaluations.organization_id",
                "offer_evaluations.rfq_id",
                "offer_evaluations.evaluation_id",
                "offer_evaluations.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rfq_id", "rfq_requirement_id"],
            [
                "rfq_requirements.organization_id",
                "rfq_requirements.rfq_id",
                "rfq_requirements.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "offer_evaluation_id", "rfq_requirement_id"),
        UniqueConstraint("organization_id", "evaluation_id", "id"),
        UniqueConstraint("organization_id", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    offer_evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_requirement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    outcome: Mapped[RequirementOutcome] = mapped_column(
        enum_type(RequirementOutcome, "requirement_check_outcome"), nullable=False
    )
    is_mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)


class RequirementCheckEvidence(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "requirement_check_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "evaluation_id", "requirement_check_id"],
            [
                "requirement_checks.organization_id",
                "requirement_checks.evaluation_id",
                "requirement_checks.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "evidence_anchor_id"],
            ["evidence_anchors.organization_id", "evidence_anchors.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "requirement_check_id", "evidence_anchor_id"),
        UniqueConstraint("organization_id", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evaluation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requirement_check_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_anchor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
