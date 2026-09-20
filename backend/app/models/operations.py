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
    Index,
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


def enum_type(enum: type[StrEnum], name: str, *, length: int = 40) -> Enum:
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        length=length,
        values_callable=lambda enum_class: [member.value for member in enum_class],
    )


class PurchaseOrderStatus(StrEnum):
    DRAFT = "draft"
    PENDING_AUTHORIZATION = "pending_authorization"
    AUTHORIZED = "authorized"
    ISSUED = "issued"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"
    CLOSED = "closed"


class PurchaseOrderVersionStatus(StrEnum):
    DRAFT = "draft"
    PENDING_AUTHORIZATION = "pending_authorization"
    AUTHORIZED = "authorized"
    ISSUED = "issued"
    ACKNOWLEDGED = "acknowledged"
    SUPERSEDED = "superseded"


class SupplierAcknowledgement(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    CHANGES_PROPOSED = "changes_proposed"


class ReceiptStatus(StrEnum):
    RECORDED = "recorded"
    RETURNED_IN_PART = "returned_in_part"
    FULLY_RETURNED = "fully_returned"


class InvoiceStatus(StrEnum):
    CAPTURED = "captured"
    DUPLICATE_SUSPECTED = "duplicate_suspected"
    MATCHED = "matched"
    MISMATCH = "mismatch"
    APPROVED_FOR_EXPORT = "approved_for_export"
    EXPORTED = "exported"
    VOIDED = "voided"


class MatchMode(StrEnum):
    TWO_WAY = "two_way"
    THREE_WAY = "three_way"


class MatchOutcome(StrEnum):
    MATCHED = "matched"
    MISMATCH = "mismatch"


class ExceptionKind(StrEnum):
    DUPLICATE_INVOICE = "duplicate_invoice"
    CURRENCY = "currency"
    QUANTITY = "quantity"
    PRICE = "price"
    TAX = "tax"
    FREIGHT = "freight"
    TOTAL = "total"


class AccountingExportStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    RECONCILED = "reconciled"


class ReconciliationStatus(StrEnum):
    PENDING = "pending"
    RECONCILED = "reconciled"
    MISMATCH = "mismatch"


class PurchaseOrder(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "award_id"],
            ["awards.organization_id", "awards.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "po_number"),
        UniqueConstraint("organization_id", "award_id", "supplier_id"),
        UniqueConstraint("organization_id", "creation_idempotency_key"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("current_revision > 0", name="positive_current_revision"),
        CheckConstraint("total_amount >= 0", name="nonnegative_total_amount"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso_code"),
        CheckConstraint("length(content_digest) = 64", name="content_digest_length"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    award_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    po_number: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[PurchaseOrderStatus] = mapped_column(
        enum_type(PurchaseOrderStatus, "purchase_order_status"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    creation_idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PurchaseOrderVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "purchase_order_versions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "purchase_order_id"],
            ["purchase_orders.organization_id", "purchase_orders.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "purchase_order_id", "revision"),
        UniqueConstraint("organization_id", "purchase_order_id", "id"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("revision > 0", name="positive_revision"),
        CheckConstraint("total_amount >= 0", name="nonnegative_total_amount"),
        CheckConstraint("length(content_digest) = 64", name="content_digest_length"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[PurchaseOrderVersionStatus] = mapped_column(
        enum_type(PurchaseOrderVersionStatus, "purchase_order_version_status"), nullable=False
    )
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    material_change: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    amendment_reason: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    authorized_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledgement: Mapped[SupplierAcknowledgement | None] = mapped_column(
        enum_type(SupplierAcknowledgement, "supplier_acknowledgement")
    )
    acknowledgement_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PurchaseOrderLine(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "purchase_order_id", "purchase_order_version_id"],
            [
                "purchase_order_versions.organization_id",
                "purchase_order_versions.purchase_order_id",
                "purchase_order_versions.id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "rfq_item_id"],
            ["rfq_items.organization_id", "rfq_items.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "purchase_order_version_id", "line_number"),
        UniqueConstraint("organization_id", "purchase_order_version_id", "id"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("line_number > 0", name="positive_line_number"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("unit_price >= 0", name="nonnegative_unit_price"),
        CheckConstraint("tax_amount >= 0", name="nonnegative_tax_amount"),
        CheckConstraint("freight_amount >= 0", name="nonnegative_freight_amount"),
        CheckConstraint("line_total >= 0", name="nonnegative_line_total"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    purchase_order_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    rfq_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    freight_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)


class DeliveryReceipt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "delivery_receipts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "purchase_order_id"],
            ["purchase_orders.organization_id", "purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "purchase_order_id", "purchase_order_version_id"],
            [
                "purchase_order_versions.organization_id",
                "purchase_order_versions.purchase_order_id",
                "purchase_order_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "receipt_number"),
        UniqueConstraint("organization_id", "idempotency_key"),
        CheckConstraint("version > 0", name="positive_version"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    purchase_order_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    receipt_number: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[ReceiptStatus] = mapped_column(
        enum_type(ReceiptStatus, "delivery_receipt_status"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    received_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class DeliveryReceiptLine(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "delivery_receipt_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "receipt_id"],
            ["delivery_receipts.organization_id", "delivery_receipts.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "purchase_order_version_id", "purchase_order_line_id"],
            [
                "purchase_order_lines.organization_id",
                "purchase_order_lines.purchase_order_version_id",
                "purchase_order_lines.id",
            ],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "receipt_id", "purchase_order_line_id"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("accepted_quantity >= 0", name="nonnegative_accepted_quantity"),
        CheckConstraint("rejected_quantity >= 0", name="nonnegative_rejected_quantity"),
        CheckConstraint(
            "accepted_quantity + rejected_quantity > 0", name="positive_delivered_quantity"
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    receipt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    purchase_order_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    purchase_order_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    accepted_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    rejected_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    inspection_note: Mapped[str | None] = mapped_column(Text)


class ReceiptReturn(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "receipt_returns"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "receipt_line_id"],
            ["delivery_receipt_lines.organization_id", "delivery_receipt_lines.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "idempotency_key"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    receipt_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    returned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class Invoice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "purchase_order_id"],
            ["purchase_orders.organization_id", "purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "capture_idempotency_key"),
        Index(
            "ix_invoices_duplicate_review",
            "organization_id",
            "supplier_id",
            "normalized_invoice_number",
        ),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("subtotal >= 0", name="nonnegative_subtotal"),
        CheckConstraint("tax_amount >= 0", name="nonnegative_tax_amount"),
        CheckConstraint("freight_amount >= 0", name="nonnegative_freight_amount"),
        CheckConstraint("total_amount >= 0", name="nonnegative_total_amount"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso_code"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supplier_invoice_number: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_invoice_number: Mapped[str] = mapped_column(String(120), nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    freight_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(
        enum_type(InvoiceStatus, "invoice_status"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    capture_idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    captured_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class InvoiceLine(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "invoice_id"],
            ["invoices.organization_id", "invoices.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "purchase_order_line_id"],
            ["purchase_order_lines.organization_id", "purchase_order_lines.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "invoice_id", "line_number"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("line_number > 0", name="positive_line_number"),
        CheckConstraint("quantity > 0", name="positive_quantity"),
        CheckConstraint("unit_price >= 0", name="nonnegative_unit_price"),
        CheckConstraint("tax_amount >= 0", name="nonnegative_tax_amount"),
        CheckConstraint("freight_amount >= 0", name="nonnegative_freight_amount"),
        CheckConstraint("line_total >= 0", name="nonnegative_line_total"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    purchase_order_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    freight_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)


class InvoiceMatch(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "invoice_matches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "invoice_id"],
            ["invoices.organization_id", "invoices.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "invoice_id", "attempt"),
        UniqueConstraint("organization_id", "idempotency_key"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("attempt > 0", name="positive_attempt"),
        CheckConstraint("length(input_digest) = 64", name="input_digest_length"),
        CheckConstraint("quantity_tolerance >= 0", name="nonnegative_quantity_tolerance"),
        CheckConstraint("amount_tolerance >= 0", name="nonnegative_amount_tolerance"),
        CheckConstraint(
            "percent_tolerance >= 0 AND percent_tolerance <= 100",
            name="valid_percent_tolerance",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[MatchMode] = mapped_column(
        enum_type(MatchMode, "invoice_match_mode"), nullable=False
    )
    outcome: Mapped[MatchOutcome] = mapped_column(
        enum_type(MatchOutcome, "invoice_match_outcome"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    input_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity_tolerance: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    amount_tolerance: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    percent_tolerance: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    matched_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class MatchException(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "match_exceptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "match_id"],
            ["invoice_matches.organization_id", "invoice_matches.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "invoice_line_id"],
            ["invoice_lines.organization_id", "invoice_lines.id"],
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    match_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invoice_line_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[ExceptionKind] = mapped_column(
        enum_type(ExceptionKind, "match_exception_kind"), nullable=False
    )
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    expected_value: Mapped[str | None] = mapped_column(String(200))
    actual_value: Mapped[str | None] = mapped_column(String(200))
    variance: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    resolution: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AccountingExport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "accounting_exports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "invoice_id"],
            ["invoices.organization_id", "invoices.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "invoice_id"),
        UniqueConstraint("organization_id", "external_reference"),
        UniqueConstraint("organization_id", "idempotency_key"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("version > 0", name="positive_version"),
        CheckConstraint("attempt_count >= 0", name="nonnegative_attempt_count"),
        CheckConstraint("length(payload_digest) = 64", name="payload_digest_length"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False, default="sandbox")
    external_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(160))
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[AccountingExportStatus] = mapped_column(
        enum_type(AccountingExportStatus, "accounting_export_status"), nullable=False
    )
    reconciliation_status: Mapped[ReconciliationStatus] = mapped_column(
        enum_type(ReconciliationStatus, "accounting_reconciliation_status"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class AccountingSandboxEntry(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "accounting_sandbox_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "export_id"],
            ["accounting_exports.organization_id", "accounting_exports.id"],
            ondelete="RESTRICT",
        ),
        UniqueConstraint("organization_id", "external_reference"),
        UniqueConstraint("organization_id", "export_id"),
        UniqueConstraint("organization_id", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    export_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    external_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    external_id: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
