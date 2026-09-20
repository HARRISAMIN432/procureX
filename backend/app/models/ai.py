import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
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


class AnalysisRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STALE = "stale"


class InvocationStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "evaluation_id"],
            ["evaluations.organization_id", "evaluations.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "thread_id"),
        UniqueConstraint("organization_id", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    graph_name: Mapped[str] = mapped_column(String(120), nullable=False)
    graph_version: Mapped[str] = mapped_column(String(80), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    evaluation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_digest: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[AnalysisRunStatus] = mapped_column(
        enum_type(AnalysisRunStatus, "analysis_run_status"),
        nullable=False,
        default=AnalysisRunStatus.QUEUED,
        server_default=AnalysisRunStatus.QUEUED.value,
    )
    input: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    output: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_detail: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class ModelInvocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "model_invocations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "analysis_run_id"],
            ["analysis_runs.organization_id", "analysis_runs.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("input_tokens >= 0", name="nonnegative_input_tokens"),
        CheckConstraint("output_tokens >= 0", name="nonnegative_output_tokens"),
        CheckConstraint("cost_amount >= 0", name="nonnegative_cost"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    node_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[InvocationStatus] = mapped_column(
        enum_type(InvocationStatus, "model_invocation_status"), nullable=False
    )
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    cost_currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    provider_request_id: Mapped[str | None] = mapped_column(String(255))
    error_code: Mapped[str | None] = mapped_column(String(100))
