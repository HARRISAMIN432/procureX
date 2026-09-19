import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
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


class DocumentStatus(StrEnum):
    QUARANTINED = "quarantined"
    SCANNING = "scanning"
    READY = "ready"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class DocumentVersionStatus(StrEnum):
    QUARANTINED = "quarantined"
    SCANNING = "scanning"
    PARSING = "parsing"
    EXTRACTED = "extracted"
    REVIEWED = "reviewed"
    REJECTED = "rejected"
    FAILED = "failed"


class AssetStatus(StrEnum):
    UPLOADED = "uploaded"
    VERIFIED = "verified"
    DELETION_PENDING = "deletion_pending"
    DELETED = "deleted"
    MISSING = "missing"


class ScanStatus(StrEnum):
    PENDING = "pending"
    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("organization_id", "id"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        enum_type(DocumentStatus, "document_status"),
        nullable=False,
        default=DocumentStatus.QUARANTINED,
        server_default=DocumentStatus.QUARANTINED.value,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class DocumentVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "document_id", "version"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("byte_size >= 0", name="nonnegative_byte_size"),
        CheckConstraint("length(sha256) = 64", name="sha256_length"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[str] = mapped_column(String(150), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[DocumentVersionStatus] = mapped_column(
        enum_type(DocumentVersionStatus, "document_version_status"),
        nullable=False,
        default=DocumentVersionStatus.QUARANTINED,
        server_default=DocumentVersionStatus.QUARANTINED.value,
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    upload_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CloudinaryAsset(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "cloudinary_assets"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "document_version_id"),
        UniqueConstraint("cloudinary_asset_id"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("delivery_type = 'authenticated'", name="authenticated_delivery"),
        CheckConstraint("byte_size >= 0", name="nonnegative_byte_size"),
        Index("ix_cloudinary_assets_public_id", "public_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    cloudinary_asset_id: Mapped[str] = mapped_column(String(255), nullable=False)
    public_id: Mapped[str] = mapped_column(String(500), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False, default="raw")
    delivery_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="authenticated", server_default="authenticated"
    )
    provider_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    format: Mapped[str | None] = mapped_column(String(50))
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    upload_response_signature: Mapped[str | None] = mapped_column(String(255))
    backup_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[AssetStatus] = mapped_column(
        enum_type(AssetStatus, "cloudinary_asset_status"),
        nullable=False,
        default=AssetStatus.UPLOADED,
        server_default=AssetStatus.UPLOADED.value,
    )


class DocumentScan(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "document_scans"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "document_version_id", "scanner", "scanner_version"),
        UniqueConstraint("organization_id", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    scanner: Mapped[str] = mapped_column(String(100), nullable=False)
    scanner_version: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[ScanStatus] = mapped_column(
        enum_type(ScanStatus, "document_scan_status"), nullable=False
    )
    result: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
