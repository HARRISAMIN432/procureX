import uuid
from datetime import date, datetime
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


class SupplierStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    SUSPENDED = "suspended"
    REJECTED = "rejected"


class QualificationStatus(StrEnum):
    PENDING = "pending"
    QUALIFIED = "qualified"
    UNQUALIFIED = "unqualified"
    EXPIRED = "expired"


class CertificateStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Supplier(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "suppliers"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "registration_country", "registration_number"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint(
            "registration_country ~ '^[A-Z]{2}$'", name="registration_country_iso_code"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    legal_name: Mapped[str] = mapped_column(String(250), nullable=False)
    trading_name: Mapped[str | None] = mapped_column(String(250))
    registration_country: Mapped[str] = mapped_column(String(2), nullable=False)
    registration_number: Mapped[str] = mapped_column(String(120), nullable=False)
    tax_identifier: Mapped[str | None] = mapped_column(String(120))
    website: Mapped[str | None] = mapped_column(String(500))
    categories: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    capabilities: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[SupplierStatus] = mapped_column(
        enum_type(SupplierStatus, "supplier_status"),
        nullable=False,
        default=SupplierStatus.PENDING,
        server_default=SupplierStatus.PENDING.value,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status_reason: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class SupplierContact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "supplier_contacts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "supplier_id", "email"),
        UniqueConstraint("organization_id", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50))
    title: Mapped[str | None] = mapped_column(String(150))
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class SupplierQualification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "supplier_qualifications"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "supplier_id", "category"),
        UniqueConstraint("organization_id", "supplier_id", "id"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from", name="valid_period"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    category: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[QualificationStatus] = mapped_column(
        enum_type(QualificationStatus, "supplier_qualification_status"),
        nullable=False,
        default=QualificationStatus.PENDING,
        server_default=QualificationStatus.PENDING.value,
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    assessment_notes: Mapped[str | None] = mapped_column(Text)
    assessed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SupplierCertificate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "supplier_certificates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "supplier_id", "qualification_id"],
            [
                "supplier_qualifications.organization_id",
                "supplier_qualifications.supplier_id",
                "supplier_qualifications.id",
            ],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "organization_id", "supplier_id", "certificate_type", "certificate_number"
        ),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint(
            "expires_on IS NULL OR issued_on IS NULL OR expires_on >= issued_on",
            name="valid_period",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    qualification_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    certificate_type: Mapped[str] = mapped_column(String(120), nullable=False)
    certificate_number: Mapped[str] = mapped_column(String(150), nullable=False)
    issuer: Mapped[str] = mapped_column(String(250), nullable=False)
    issued_on: Mapped[date | None] = mapped_column(Date)
    expires_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[CertificateStatus] = mapped_column(
        enum_type(CertificateStatus, "supplier_certificate_status"),
        nullable=False,
        default=CertificateStatus.PENDING,
        server_default=CertificateStatus.PENDING.value,
    )
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
