from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.operations import (
    AccountingExportStatus,
    ExceptionKind,
    InvoiceStatus,
    MatchMode,
    MatchOutcome,
    PurchaseOrderStatus,
    PurchaseOrderVersionStatus,
    ReceiptStatus,
    ReconciliationStatus,
    SupplierAcknowledgement,
)


class PurchaseOrderCreate(BaseModel):
    supplier_id: UUID
    expected_award_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_key: str = Field(min_length=8, max_length=200)
    delivery_terms: str | None = Field(default=None, max_length=5000)


class PurchaseOrderLineWrite(BaseModel):
    source_line_id: UUID
    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    unit: str = Field(min_length=1, max_length=50)
    unit_price: Decimal = Field(ge=0, max_digits=20, decimal_places=4)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=4)
    freight_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=4)

    @field_validator("description", "unit")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class PurchaseOrderAmend(BaseModel):
    expected_version: int = Field(gt=0)
    expected_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=5, max_length=5000)
    delivery_terms: str | None = Field(default=None, max_length=5000)
    lines: list[PurchaseOrderLineWrite] = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def unique_source_lines(self) -> "PurchaseOrderAmend":
        keys = [line.source_line_id for line in self.lines]
        if len(keys) != len(set(keys)):
            raise ValueError("PO amendment source lines must be unique")
        return self


class VersionCommand(BaseModel):
    expected_version: int = Field(gt=0)
    expected_content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class PurchaseOrderAcknowledge(VersionCommand):
    acknowledgement: SupplierAcknowledgement
    note: str | None = Field(default=None, max_length=5000)


class PurchaseOrderLineRead(BaseModel):
    id: UUID
    source_line_id: UUID
    line_number: int
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    tax_amount: Decimal
    freight_amount: Decimal
    line_total: Decimal


class PurchaseOrderVersionRead(BaseModel):
    id: UUID
    revision: int
    status: PurchaseOrderVersionStatus
    content_digest: str
    total_amount: Decimal
    material_change: bool
    amendment_reason: str | None
    snapshot: dict[str, object]
    lines: list[PurchaseOrderLineRead]
    authorized_at: datetime | None
    issued_at: datetime | None
    acknowledged_at: datetime | None
    acknowledgement: SupplierAcknowledgement | None
    acknowledgement_note: str | None
    created_at: datetime


class PurchaseOrderRead(BaseModel):
    id: UUID
    award_id: UUID
    supplier_id: UUID
    po_number: str
    status: PurchaseOrderStatus
    version: int
    current_revision: int
    currency: str
    total_amount: Decimal
    content_digest: str
    issued_at: datetime | None
    acknowledged_at: datetime | None
    current: PurchaseOrderVersionRead
    created_at: datetime
    updated_at: datetime


class ReceiptLineWrite(BaseModel):
    purchase_order_line_id: UUID
    accepted_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    rejected_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    inspection_note: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def delivered_quantity_is_positive(self) -> "ReceiptLineWrite":
        if self.accepted_quantity + self.rejected_quantity <= 0:
            raise ValueError("A receipt line must contain accepted or rejected quantity")
        return self


class ReceiptCreate(BaseModel):
    expected_po_version: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=200)
    received_at: datetime
    note: str | None = Field(default=None, max_length=5000)
    lines: list[ReceiptLineWrite] = Field(min_length=1, max_length=5000)

    @field_validator("received_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("received_at must include a timezone")
        return value

    @model_validator(mode="after")
    def unique_po_lines(self) -> "ReceiptCreate":
        keys = [line.purchase_order_line_id for line in self.lines]
        if len(keys) != len(set(keys)):
            raise ValueError("Receipt lines must be unique")
        return self


class ReceiptLineRead(BaseModel):
    id: UUID
    purchase_order_line_id: UUID
    accepted_quantity: Decimal
    rejected_quantity: Decimal
    returned_quantity: Decimal
    inspection_note: str | None


class ReceiptRead(BaseModel):
    id: UUID
    purchase_order_id: UUID
    purchase_order_version_id: UUID
    receipt_number: str
    status: ReceiptStatus
    version: int
    received_at: datetime
    note: str | None
    lines: list[ReceiptLineRead]
    created_at: datetime


class ReturnCreate(BaseModel):
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    reason: str = Field(min_length=3, max_length=5000)
    idempotency_key: str = Field(min_length=8, max_length=200)
    returned_at: datetime

    @field_validator("returned_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("returned_at must include a timezone")
        return value


class ReturnRead(BaseModel):
    id: UUID
    receipt_line_id: UUID
    quantity: Decimal
    reason: str
    returned_at: datetime
    created_at: datetime


class InvoiceLineWrite(BaseModel):
    purchase_order_line_id: UUID
    description: str = Field(min_length=1, max_length=500)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    unit_price: Decimal = Field(ge=0, max_digits=20, decimal_places=4)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=4)
    freight_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=20, decimal_places=4)


class InvoiceCapture(BaseModel):
    supplier_invoice_number: str = Field(min_length=1, max_length=120)
    invoice_date: date
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    subtotal: Decimal = Field(ge=0, max_digits=20, decimal_places=4)
    tax_amount: Decimal = Field(ge=0, max_digits=20, decimal_places=4)
    freight_amount: Decimal = Field(ge=0, max_digits=20, decimal_places=4)
    total_amount: Decimal = Field(ge=0, max_digits=20, decimal_places=4)
    idempotency_key: str = Field(min_length=8, max_length=200)
    lines: list[InvoiceLineWrite] = Field(min_length=1, max_length=5000)

    @field_validator("supplier_invoice_number")
    @classmethod
    def strip_invoice_number(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def unique_po_lines(self) -> "InvoiceCapture":
        keys = [line.purchase_order_line_id for line in self.lines]
        if len(keys) != len(set(keys)):
            raise ValueError("Invoice lines must be unique per PO line")
        return self


class InvoiceLineRead(BaseModel):
    id: UUID
    purchase_order_line_id: UUID
    line_number: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    tax_amount: Decimal
    freight_amount: Decimal
    line_total: Decimal


class InvoiceRead(BaseModel):
    id: UUID
    purchase_order_id: UUID
    supplier_id: UUID
    supplier_invoice_number: str
    invoice_date: date
    currency: str
    subtotal: Decimal
    tax_amount: Decimal
    freight_amount: Decimal
    total_amount: Decimal
    status: InvoiceStatus
    version: int
    lines: list[InvoiceLineRead]
    created_at: datetime
    updated_at: datetime


class InvoiceMatchCreate(BaseModel):
    expected_invoice_version: int = Field(gt=0)
    mode: MatchMode = MatchMode.THREE_WAY
    quantity_tolerance: Decimal = Field(default=Decimal("0"), ge=0, decimal_places=4)
    amount_tolerance: Decimal = Field(default=Decimal("0.01"), ge=0, decimal_places=4)
    percent_tolerance: Decimal = Field(default=Decimal("0"), ge=0, le=100, decimal_places=4)
    idempotency_key: str = Field(min_length=8, max_length=200)


class MatchExceptionRead(BaseModel):
    id: UUID
    invoice_line_id: UUID | None
    kind: ExceptionKind
    blocking: bool
    message: str
    expected_value: str | None
    actual_value: str | None
    variance: Decimal | None
    resolved_at: datetime | None
    resolution: str | None


class InvoiceMatchRead(BaseModel):
    id: UUID
    invoice_id: UUID
    attempt: int
    mode: MatchMode
    outcome: MatchOutcome
    input_digest: str
    quantity_tolerance: Decimal
    amount_tolerance: Decimal
    percent_tolerance: Decimal
    snapshot: dict[str, object]
    exceptions: list[MatchExceptionRead]
    created_at: datetime


class ExceptionResolve(BaseModel):
    expected_invoice_version: int = Field(gt=0)
    resolution: str = Field(min_length=5, max_length=5000)


class InvoiceApprove(BaseModel):
    expected_invoice_version: int = Field(gt=0)


class AccountingExportCreate(BaseModel):
    expected_invoice_version: int = Field(gt=0)
    idempotency_key: str = Field(min_length=8, max_length=200)


class AccountingExportRetry(BaseModel):
    expected_version: int = Field(gt=0)


class AccountingReconcile(BaseModel):
    expected_version: int = Field(gt=0)
    status: ReconciliationStatus
    note: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def terminal_status_only(self) -> "AccountingReconcile":
        if self.status is ReconciliationStatus.PENDING:
            raise ValueError("Reconciliation result must be reconciled or mismatch")
        return self


class AccountingExportRead(BaseModel):
    id: UUID
    invoice_id: UUID
    provider: str
    external_reference: str
    external_id: str | None
    payload_digest: str
    status: AccountingExportStatus
    reconciliation_status: ReconciliationStatus
    version: int
    attempt_count: int
    last_error: str | None
    exported_at: datetime | None
    reconciled_at: datetime | None
    created_at: datetime
    updated_at: datetime
