import hashlib
import json
import re
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from sqlalchemy import func, select

from app.auth.context import RequestContext
from app.models.awards import Award, AwardStatus
from app.models.operations import (
    AccountingExport,
    AccountingExportStatus,
    AccountingSandboxEntry,
    DeliveryReceipt,
    DeliveryReceiptLine,
    ExceptionKind,
    Invoice,
    InvoiceLine,
    InvoiceMatch,
    InvoiceStatus,
    MatchException,
    MatchOutcome,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
    PurchaseOrderVersion,
    PurchaseOrderVersionStatus,
    ReceiptReturn,
    ReceiptStatus,
    ReconciliationStatus,
    SupplierAcknowledgement,
)
from app.models.platform import ActorType, AuditEvent, OutboxEvent
from app.models.sourcing import RfqItem
from app.schemas.operations import (
    AccountingExportCreate,
    AccountingExportRead,
    AccountingExportRetry,
    AccountingReconcile,
    ExceptionResolve,
    InvoiceApprove,
    InvoiceCapture,
    InvoiceLineRead,
    InvoiceMatchCreate,
    InvoiceMatchRead,
    InvoiceRead,
    MatchExceptionRead,
    PurchaseOrderAcknowledge,
    PurchaseOrderAmend,
    PurchaseOrderCreate,
    PurchaseOrderLineRead,
    PurchaseOrderRead,
    PurchaseOrderVersionRead,
    ReceiptCreate,
    ReceiptLineRead,
    ReceiptRead,
    ReturnCreate,
    ReturnRead,
    VersionCommand,
)
from app.services.awards import _ensure_current

MONEY_QUANTUM = Decimal("0.0001")
ZERO = Decimal("0")


class OperationsNotFoundError(ValueError):
    pass


class OperationsConflictError(ValueError):
    pass


class OperationsValidationError(ValueError):
    pass


def digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def normalized_invoice_number(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def within_tolerance(
    actual: Decimal, expected: Decimal, amount_tolerance: Decimal, percent_tolerance: Decimal
) -> bool:
    permitted = max(amount_tolerance, abs(expected) * percent_tolerance / Decimal("100"))
    return abs(actual - expected) <= permitted


def _event(
    context: RequestContext,
    action: str,
    object_type: str,
    object_id: uuid.UUID,
    version: int,
    changes: dict[str, object],
) -> None:
    context.session.add_all(
        [
            AuditEvent(
                organization_id=context.organization_id,
                actor_type=ActorType.USER,
                actor_id=context.user_id,
                action=action,
                object_type=object_type,
                object_id=object_id,
                object_version=version,
                changes=changes,
            ),
            OutboxEvent(
                organization_id=context.organization_id,
                aggregate_type=object_type,
                aggregate_id=object_id,
                aggregate_version=version,
                event_type=action,
                schema_version=1,
                payload={"id": str(object_id), **changes},
                actor_id=context.user_id,
            ),
        ]
    )


async def _current_po_version(
    context: RequestContext, po: PurchaseOrder, *, lock: bool = False
) -> PurchaseOrderVersion:
    query = select(PurchaseOrderVersion).where(
        PurchaseOrderVersion.organization_id == context.organization_id,
        PurchaseOrderVersion.purchase_order_id == po.id,
        PurchaseOrderVersion.revision == po.current_revision,
    )
    if lock:
        query = query.with_for_update()
    version = await context.session.scalar(query)
    if version is None:
        raise OperationsConflictError("Current purchase-order version is missing")
    return version


async def _po_lines(context: RequestContext, version_id: uuid.UUID) -> list[PurchaseOrderLine]:
    return list(
        await context.session.scalars(
            select(PurchaseOrderLine)
            .where(
                PurchaseOrderLine.organization_id == context.organization_id,
                PurchaseOrderLine.purchase_order_version_id == version_id,
            )
            .order_by(PurchaseOrderLine.line_number)
        )
    )


async def _po_version_read(
    context: RequestContext, version: PurchaseOrderVersion
) -> PurchaseOrderVersionRead:
    lines = await _po_lines(context, version.id)
    snapshot_lines = cast(list[dict[str, object]], version.snapshot.get("lines", []))
    source_by_number = {
        int(str(item["line_number"])): uuid.UUID(str(item["source_line_id"]))
        for item in snapshot_lines
    }
    return PurchaseOrderVersionRead(
        id=version.id,
        revision=version.revision,
        status=version.status,
        content_digest=version.content_digest,
        total_amount=version.total_amount,
        material_change=version.material_change,
        amendment_reason=version.amendment_reason,
        snapshot=version.snapshot,
        lines=[
            PurchaseOrderLineRead(
                id=line.id,
                source_line_id=source_by_number.get(line.line_number, line.rfq_item_id),
                line_number=line.line_number,
                description=line.description,
                quantity=line.quantity,
                unit=line.unit,
                unit_price=line.unit_price,
                tax_amount=line.tax_amount,
                freight_amount=line.freight_amount,
                line_total=line.line_total,
            )
            for line in lines
        ],
        authorized_at=version.authorized_at,
        issued_at=version.issued_at,
        acknowledged_at=version.acknowledged_at,
        acknowledgement=version.acknowledgement,
        acknowledgement_note=version.acknowledgement_note,
        created_at=version.created_at,
    )


async def _po_read(context: RequestContext, po: PurchaseOrder) -> PurchaseOrderRead:
    await context.session.flush()
    await context.session.refresh(po)
    version = await _current_po_version(context, po)
    return PurchaseOrderRead(
        id=po.id,
        award_id=po.award_id,
        supplier_id=po.supplier_id,
        po_number=po.po_number,
        status=po.status,
        version=po.version,
        current_revision=po.current_revision,
        currency=po.currency,
        total_amount=po.total_amount,
        content_digest=po.content_digest,
        issued_at=po.issued_at,
        acknowledged_at=po.acknowledged_at,
        current=await _po_version_read(context, version),
        created_at=po.created_at,
        updated_at=po.updated_at,
    )


async def create_purchase_order(
    context: RequestContext, award_id: uuid.UUID, payload: PurchaseOrderCreate
) -> PurchaseOrderRead:
    existing = await context.session.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.organization_id == context.organization_id,
            PurchaseOrder.creation_idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        if existing.award_id != award_id or existing.supplier_id != payload.supplier_id:
            raise OperationsConflictError("Idempotency key was used for another purchase order")
        original = await context.session.scalar(
            select(PurchaseOrderVersion).where(
                PurchaseOrderVersion.organization_id == context.organization_id,
                PurchaseOrderVersion.purchase_order_id == existing.id,
                PurchaseOrderVersion.revision == 1,
            )
        )
        if (
            original is None
            or original.snapshot.get("award_digest") != payload.expected_award_digest
            or original.snapshot.get("delivery_terms") != payload.delivery_terms
        ):
            raise OperationsConflictError("Idempotency key was reused with changed PO content")
        return await _po_read(context, existing)

    award = await context.session.scalar(
        select(Award)
        .where(Award.organization_id == context.organization_id, Award.id == award_id)
        .with_for_update()
    )
    if award is None:
        raise OperationsNotFoundError("Award not found")
    if award.content_digest != payload.expected_award_digest:
        raise OperationsConflictError("Award digest is stale")
    if award.status is not AwardStatus.APPROVED:
        raise OperationsValidationError("Only an approved award can create a purchase order")
    if not await _ensure_current(context, award):
        raise OperationsConflictError(
            "Award inputs are no longer current; renewed approval required"
        )

    allocations = [
        item
        for item in cast(list[dict[str, object]], award.snapshot.get("allocations", []))
        if uuid.UUID(str(item["supplier_id"])) == payload.supplier_id
    ]
    if not allocations:
        raise OperationsValidationError("Supplier has no allocation in the approved award snapshot")
    if await context.session.scalar(
        select(PurchaseOrder.id).where(
            PurchaseOrder.organization_id == context.organization_id,
            PurchaseOrder.award_id == award.id,
            PurchaseOrder.supplier_id == payload.supplier_id,
        )
    ):
        raise OperationsConflictError("A purchase order already exists for this award and supplier")

    rfq_item_ids = [uuid.UUID(str(item["rfq_item_id"])) for item in allocations]
    rfq_items = list(
        await context.session.scalars(
            select(RfqItem).where(
                RfqItem.organization_id == context.organization_id,
                RfqItem.id.in_(rfq_item_ids),
            )
        )
    )
    item_by_id = {item.id: item for item in rfq_items}
    if len(item_by_id) != len(set(rfq_item_ids)):
        raise OperationsConflictError("Approved award refers to missing RFQ items")

    snapshot_lines: list[dict[str, object]] = []
    total = ZERO
    for line_number, allocation in enumerate(
        sorted(allocations, key=lambda item: str(item["rfq_item_id"])), start=1
    ):
        item_id = uuid.UUID(str(allocation["rfq_item_id"]))
        quantity = Decimal(str(allocation["quantity"]))
        unit_price = Decimal(str(allocation["unit_cost"]))
        line_total = money(quantity * unit_price)
        total += line_total
        snapshot_lines.append(
            {
                "source_line_id": str(item_id),
                "rfq_item_id": str(item_id),
                "line_number": line_number,
                "description": item_by_id[item_id].description,
                "quantity": str(quantity),
                "unit": item_by_id[item_id].unit,
                "unit_price": str(unit_price),
                "tax_amount": "0.0000",
                "freight_amount": "0.0000",
                "line_total": str(line_total),
            }
        )
    total = money(total)
    snapshot: dict[str, object] = {
        "award_id": str(award.id),
        "award_digest": award.content_digest,
        "supplier_id": str(payload.supplier_id),
        "currency": award.currency,
        "delivery_terms": payload.delivery_terms,
        "lines": snapshot_lines,
        "total_amount": str(total),
    }
    content_digest = digest(snapshot)
    po = PurchaseOrder(
        organization_id=context.organization_id,
        award_id=award.id,
        supplier_id=payload.supplier_id,
        po_number=f"PO-{datetime.now(UTC).year}-{uuid.uuid4().hex[:10].upper()}",
        status=PurchaseOrderStatus.DRAFT,
        version=1,
        current_revision=1,
        currency=award.currency,
        total_amount=total,
        content_digest=content_digest,
        creation_idempotency_key=payload.idempotency_key,
        created_by_user_id=context.user_id,
    )
    context.session.add(po)
    await context.session.flush()
    version = PurchaseOrderVersion(
        organization_id=context.organization_id,
        purchase_order_id=po.id,
        revision=1,
        status=PurchaseOrderVersionStatus.DRAFT,
        snapshot=snapshot,
        content_digest=content_digest,
        total_amount=total,
        material_change=False,
        created_by_user_id=context.user_id,
    )
    context.session.add(version)
    await context.session.flush()
    _add_po_lines(context, po.id, version.id, snapshot_lines)
    _event(
        context,
        "purchase_order.created",
        "purchase_order",
        po.id,
        po.version,
        {"award_id": str(award.id), "revision": 1, "content_digest": content_digest},
    )
    await context.session.flush()
    return await _po_read(context, po)


def _add_po_lines(
    context: RequestContext,
    po_id: uuid.UUID,
    version_id: uuid.UUID,
    lines: Sequence[dict[str, object]],
) -> None:
    for item in lines:
        context.session.add(
            PurchaseOrderLine(
                organization_id=context.organization_id,
                purchase_order_id=po_id,
                purchase_order_version_id=version_id,
                rfq_item_id=uuid.UUID(str(item["rfq_item_id"])),
                line_number=int(str(item["line_number"])),
                description=str(item["description"]),
                quantity=Decimal(str(item["quantity"])),
                unit=str(item["unit"]),
                unit_price=Decimal(str(item["unit_price"])),
                tax_amount=Decimal(str(item["tax_amount"])),
                freight_amount=Decimal(str(item["freight_amount"])),
                line_total=Decimal(str(item["line_total"])),
            )
        )


async def read_purchase_order(
    context: RequestContext, purchase_order_id: uuid.UUID
) -> PurchaseOrderRead:
    po = await context.session.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.organization_id == context.organization_id,
            PurchaseOrder.id == purchase_order_id,
        )
    )
    if po is None:
        raise OperationsNotFoundError("Purchase order not found")
    return await _po_read(context, po)


async def amend_purchase_order(
    context: RequestContext, purchase_order_id: uuid.UUID, payload: PurchaseOrderAmend
) -> PurchaseOrderRead:
    po = await _locked_po(context, purchase_order_id, payload.expected_version)
    if po.content_digest != payload.expected_content_digest:
        raise OperationsConflictError("Purchase-order content digest is stale")
    if po.status in {PurchaseOrderStatus.CANCELLED, PurchaseOrderStatus.CLOSED}:
        raise OperationsConflictError("Purchase order can no longer be amended")
    if await context.session.scalar(
        select(DeliveryReceipt.id).where(
            DeliveryReceipt.organization_id == context.organization_id,
            DeliveryReceipt.purchase_order_id == po.id,
        )
    ):
        raise OperationsValidationError("A purchase order with receipts cannot be amended")

    current = await _current_po_version(context, po, lock=True)
    current_lines = await _po_lines(context, current.id)
    by_id = {line.id: line for line in current_lines}
    if set(by_id) != {item.source_line_id for item in payload.lines}:
        raise OperationsValidationError("Amendment must contain every current PO line exactly once")
    material = False
    snapshot_lines: list[dict[str, object]] = []
    total = ZERO
    for line_number, item in enumerate(payload.lines, start=1):
        source = by_id[item.source_line_id]
        if any(
            (
                item.quantity != source.quantity,
                item.unit_price != source.unit_price,
                item.tax_amount != source.tax_amount,
                item.freight_amount != source.freight_amount,
            )
        ):
            material = True
        line_total = money(item.quantity * item.unit_price + item.tax_amount + item.freight_amount)
        total += line_total
        snapshot_lines.append(
            {
                "source_line_id": str(source.id),
                "rfq_item_id": str(source.rfq_item_id),
                "line_number": line_number,
                "description": item.description,
                "quantity": str(item.quantity),
                "unit": item.unit,
                "unit_price": str(item.unit_price),
                "tax_amount": str(item.tax_amount),
                "freight_amount": str(item.freight_amount),
                "line_total": str(line_total),
            }
        )
    total = money(total)
    snapshot: dict[str, object] = {
        "award_id": str(po.award_id),
        "parent_revision": current.revision,
        "parent_digest": current.content_digest,
        "supplier_id": str(po.supplier_id),
        "currency": po.currency,
        "delivery_terms": payload.delivery_terms,
        "lines": snapshot_lines,
        "total_amount": str(total),
        "amendment_reason": payload.reason.strip(),
        "material_change": material,
    }
    new_digest = digest(snapshot)
    current.status = PurchaseOrderVersionStatus.SUPERSEDED
    new_status = (
        PurchaseOrderVersionStatus.PENDING_AUTHORIZATION
        if material
        else PurchaseOrderVersionStatus.DRAFT
    )
    revision = po.current_revision + 1
    version = PurchaseOrderVersion(
        organization_id=context.organization_id,
        purchase_order_id=po.id,
        revision=revision,
        status=new_status,
        snapshot=snapshot,
        content_digest=new_digest,
        total_amount=total,
        material_change=material,
        amendment_reason=payload.reason.strip(),
        created_by_user_id=context.user_id,
    )
    context.session.add(version)
    await context.session.flush()
    _add_po_lines(context, po.id, version.id, snapshot_lines)
    po.current_revision = revision
    po.content_digest = new_digest
    po.total_amount = total
    po.status = PurchaseOrderStatus.PENDING_AUTHORIZATION if material else PurchaseOrderStatus.DRAFT
    po.version += 1
    _event(
        context,
        "purchase_order.amended",
        "purchase_order",
        po.id,
        po.version,
        {
            "revision": revision,
            "material_change": material,
            "content_digest": new_digest,
        },
    )
    await context.session.flush()
    return await _po_read(context, po)


async def authorize_purchase_order_amendment(
    context: RequestContext, purchase_order_id: uuid.UUID, payload: VersionCommand
) -> PurchaseOrderRead:
    po = await _locked_po(context, purchase_order_id, payload.expected_version)
    current = await _current_po_version(context, po, lock=True)
    _require_digest(po, payload.expected_content_digest)
    if po.status is not PurchaseOrderStatus.PENDING_AUTHORIZATION or not current.material_change:
        raise OperationsConflictError(
            "Purchase order has no material amendment awaiting authorization"
        )
    if current.created_by_user_id == context.user_id:
        raise OperationsValidationError("Amendment preparer cannot authorize a material change")
    now = datetime.now(UTC)
    current.status = PurchaseOrderVersionStatus.AUTHORIZED
    current.authorized_by_user_id = context.user_id
    current.authorized_at = now
    po.status = PurchaseOrderStatus.AUTHORIZED
    po.version += 1
    _event(
        context,
        "purchase_order.amendment_authorized",
        "purchase_order",
        po.id,
        po.version,
        {"revision": current.revision, "content_digest": current.content_digest},
    )
    return await _po_read(context, po)


async def issue_purchase_order(
    context: RequestContext, purchase_order_id: uuid.UUID, payload: VersionCommand
) -> PurchaseOrderRead:
    po = await _locked_po(context, purchase_order_id, payload.expected_version)
    current = await _current_po_version(context, po, lock=True)
    _require_digest(po, payload.expected_content_digest)
    if po.status not in {PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.AUTHORIZED}:
        raise OperationsConflictError("Only a draft or authorized purchase order can be issued")
    if current.material_change and current.status is not PurchaseOrderVersionStatus.AUTHORIZED:
        raise OperationsValidationError("Material amendment requires renewed authorization")
    now = datetime.now(UTC)
    current.status = PurchaseOrderVersionStatus.ISSUED
    current.issued_at = now
    po.status = PurchaseOrderStatus.ISSUED
    po.issued_at = now
    po.version += 1
    _event(
        context,
        "purchase_order.issued",
        "purchase_order",
        po.id,
        po.version,
        {"revision": current.revision, "content_digest": current.content_digest},
    )
    return await _po_read(context, po)


async def acknowledge_purchase_order(
    context: RequestContext, purchase_order_id: uuid.UUID, payload: PurchaseOrderAcknowledge
) -> PurchaseOrderRead:
    po = await _locked_po(context, purchase_order_id, payload.expected_version)
    current = await _current_po_version(context, po, lock=True)
    _require_digest(po, payload.expected_content_digest)
    if po.status is not PurchaseOrderStatus.ISSUED:
        raise OperationsConflictError("Only an issued purchase order can be acknowledged")
    now = datetime.now(UTC)
    current.acknowledgement = payload.acknowledgement
    current.acknowledgement_note = payload.note.strip() if payload.note else None
    current.acknowledged_at = now
    po.acknowledged_at = now
    if payload.acknowledgement is SupplierAcknowledgement.ACCEPTED:
        current.status = PurchaseOrderVersionStatus.ACKNOWLEDGED
        po.status = PurchaseOrderStatus.ACKNOWLEDGED
    po.version += 1
    _event(
        context,
        f"purchase_order.{payload.acknowledgement.value}",
        "purchase_order",
        po.id,
        po.version,
        {"revision": current.revision, "note": current.acknowledgement_note},
    )
    return await _po_read(context, po)


async def _locked_po(
    context: RequestContext, po_id: uuid.UUID, expected_version: int
) -> PurchaseOrder:
    po = await context.session.scalar(
        select(PurchaseOrder)
        .where(
            PurchaseOrder.organization_id == context.organization_id,
            PurchaseOrder.id == po_id,
        )
        .with_for_update()
    )
    if po is None:
        raise OperationsNotFoundError("Purchase order not found")
    if po.version != expected_version:
        raise OperationsConflictError("Purchase-order version is stale")
    return po


def _require_digest(po: PurchaseOrder, expected: str) -> None:
    if po.content_digest != expected:
        raise OperationsConflictError("Purchase-order content digest is stale")


async def create_receipt(
    context: RequestContext, purchase_order_id: uuid.UUID, payload: ReceiptCreate
) -> ReceiptRead:
    existing = await context.session.scalar(
        select(DeliveryReceipt).where(
            DeliveryReceipt.organization_id == context.organization_id,
            DeliveryReceipt.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        if existing.purchase_order_id != purchase_order_id:
            raise OperationsConflictError("Idempotency key was used for another receipt")
        existing_read = await _receipt_read(context, existing)
        received = {
            (line.purchase_order_line_id, line.accepted_quantity, line.rejected_quantity)
            for line in existing_read.lines
        }
        requested = {
            (line.purchase_order_line_id, line.accepted_quantity, line.rejected_quantity)
            for line in payload.lines
        }
        if (
            existing.received_at != payload.received_at
            or existing.note != (payload.note.strip() if payload.note else None)
            or received != requested
        ):
            raise OperationsConflictError("Idempotency key was reused with changed receipt content")
        return existing_read
    po = await _locked_po(context, purchase_order_id, payload.expected_po_version)
    if po.status not in {
        PurchaseOrderStatus.ISSUED,
        PurchaseOrderStatus.ACKNOWLEDGED,
        PurchaseOrderStatus.PARTIALLY_RECEIVED,
        PurchaseOrderStatus.RECEIVED,
    }:
        raise OperationsConflictError("Purchase order is not open for receipts")
    current = await _current_po_version(context, po)
    current_lines = await _po_lines(context, current.id)
    line_by_id = {line.id: line for line in current_lines}
    if any(item.purchase_order_line_id not in line_by_id for item in payload.lines):
        raise OperationsValidationError("Receipt lines must belong to the current PO version")
    prior_rows = (
        await context.session.execute(
            select(
                DeliveryReceiptLine.purchase_order_line_id,
                func.coalesce(
                    func.sum(
                        DeliveryReceiptLine.accepted_quantity
                        + DeliveryReceiptLine.rejected_quantity
                    ),
                    0,
                ),
            )
            .join(
                DeliveryReceipt,
                (DeliveryReceipt.organization_id == DeliveryReceiptLine.organization_id)
                & (DeliveryReceipt.id == DeliveryReceiptLine.receipt_id),
            )
            .where(
                DeliveryReceiptLine.organization_id == context.organization_id,
                DeliveryReceipt.purchase_order_id == po.id,
            )
            .group_by(DeliveryReceiptLine.purchase_order_line_id)
        )
    ).all()
    prior: dict[uuid.UUID, Decimal] = {
        line_id: Decimal(str(quantity)) for line_id, quantity in prior_rows
    }
    for item in payload.lines:
        ordered = line_by_id[item.purchase_order_line_id].quantity
        cumulative = Decimal(str(prior.get(item.purchase_order_line_id, ZERO)))
        if cumulative + item.accepted_quantity + item.rejected_quantity > ordered:
            raise OperationsValidationError("Receipt would exceed the ordered quantity")
    count = (
        await context.session.scalar(
            select(func.count(DeliveryReceipt.id)).where(
                DeliveryReceipt.organization_id == context.organization_id,
                DeliveryReceipt.purchase_order_id == po.id,
            )
        )
        or 0
    )
    receipt = DeliveryReceipt(
        organization_id=context.organization_id,
        purchase_order_id=po.id,
        purchase_order_version_id=current.id,
        receipt_number=f"{po.po_number}-GRN-{count + 1:03d}",
        status=ReceiptStatus.RECORDED,
        version=1,
        idempotency_key=payload.idempotency_key,
        received_at=payload.received_at,
        note=payload.note.strip() if payload.note else None,
        received_by_user_id=context.user_id,
    )
    context.session.add(receipt)
    await context.session.flush()
    for item in payload.lines:
        context.session.add(
            DeliveryReceiptLine(
                organization_id=context.organization_id,
                receipt_id=receipt.id,
                purchase_order_version_id=current.id,
                purchase_order_line_id=item.purchase_order_line_id,
                accepted_quantity=item.accepted_quantity,
                rejected_quantity=item.rejected_quantity,
                inspection_note=item.inspection_note,
            )
        )
    await context.session.flush()
    po.version += 1
    await _refresh_po_receipt_status(context, po, current_lines)
    _event(
        context,
        "delivery_receipt.recorded",
        "purchase_order",
        po.id,
        po.version,
        {"receipt_id": str(receipt.id), "receipt_number": receipt.receipt_number},
    )
    return await _receipt_read(context, receipt)


async def _refresh_po_receipt_status(
    context: RequestContext, po: PurchaseOrder, current_lines: Sequence[PurchaseOrderLine]
) -> None:
    accepted_rows = (
        await context.session.execute(
            select(
                DeliveryReceiptLine.purchase_order_line_id,
                func.coalesce(func.sum(DeliveryReceiptLine.accepted_quantity), 0),
            )
            .join(
                DeliveryReceipt,
                (DeliveryReceipt.organization_id == DeliveryReceiptLine.organization_id)
                & (DeliveryReceipt.id == DeliveryReceiptLine.receipt_id),
            )
            .where(
                DeliveryReceiptLine.organization_id == context.organization_id,
                DeliveryReceipt.purchase_order_id == po.id,
            )
            .group_by(DeliveryReceiptLine.purchase_order_line_id)
        )
    ).all()
    accepted = {line_id: Decimal(str(quantity)) for line_id, quantity in accepted_rows}
    return_rows = (
        await context.session.execute(
            select(
                DeliveryReceiptLine.purchase_order_line_id,
                func.coalesce(func.sum(ReceiptReturn.quantity), 0),
            )
            .join(
                ReceiptReturn,
                (ReceiptReturn.organization_id == DeliveryReceiptLine.organization_id)
                & (ReceiptReturn.receipt_line_id == DeliveryReceiptLine.id),
            )
            .where(DeliveryReceiptLine.organization_id == context.organization_id)
            .group_by(DeliveryReceiptLine.purchase_order_line_id)
        )
    ).all()
    returned = {line_id: Decimal(str(quantity)) for line_id, quantity in return_rows}
    net = {
        line.id: accepted.get(line.id, ZERO) - returned.get(line.id, ZERO) for line in current_lines
    }
    if current_lines and all(net[line.id] >= line.quantity for line in current_lines):
        po.status = PurchaseOrderStatus.RECEIVED
    elif any(value > 0 for value in net.values()):
        po.status = PurchaseOrderStatus.PARTIALLY_RECEIVED
    elif po.acknowledged_at is not None:
        po.status = PurchaseOrderStatus.ACKNOWLEDGED
    else:
        po.status = PurchaseOrderStatus.ISSUED


async def _receipt_read(context: RequestContext, receipt: DeliveryReceipt) -> ReceiptRead:
    lines = list(
        await context.session.scalars(
            select(DeliveryReceiptLine)
            .where(
                DeliveryReceiptLine.organization_id == context.organization_id,
                DeliveryReceiptLine.receipt_id == receipt.id,
            )
            .order_by(DeliveryReceiptLine.id)
        )
    )
    return_rows = (
        (
            await context.session.execute(
                select(
                    ReceiptReturn.receipt_line_id,
                    func.coalesce(func.sum(ReceiptReturn.quantity), 0),
                )
                .where(
                    ReceiptReturn.organization_id == context.organization_id,
                    ReceiptReturn.receipt_line_id.in_([line.id for line in lines]),
                )
                .group_by(ReceiptReturn.receipt_line_id)
            )
        ).all()
        if lines
        else []
    )
    return_quantities: dict[uuid.UUID, Decimal] = {
        line_id: Decimal(str(quantity)) for line_id, quantity in return_rows
    }
    return ReceiptRead(
        id=receipt.id,
        purchase_order_id=receipt.purchase_order_id,
        purchase_order_version_id=receipt.purchase_order_version_id,
        receipt_number=receipt.receipt_number,
        status=receipt.status,
        version=receipt.version,
        received_at=receipt.received_at,
        note=receipt.note,
        lines=[
            ReceiptLineRead(
                id=line.id,
                purchase_order_line_id=line.purchase_order_line_id,
                accepted_quantity=line.accepted_quantity,
                rejected_quantity=line.rejected_quantity,
                returned_quantity=Decimal(str(return_quantities.get(line.id, ZERO))),
                inspection_note=line.inspection_note,
            )
            for line in lines
        ],
        created_at=receipt.created_at,
    )


async def create_return(
    context: RequestContext, receipt_line_id: uuid.UUID, payload: ReturnCreate
) -> ReturnRead:
    existing = await context.session.scalar(
        select(ReceiptReturn).where(
            ReceiptReturn.organization_id == context.organization_id,
            ReceiptReturn.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        if existing.receipt_line_id != receipt_line_id:
            raise OperationsConflictError("Idempotency key was used for another return")
        if (
            existing.quantity != payload.quantity
            or existing.reason != payload.reason.strip()
            or existing.returned_at != payload.returned_at
        ):
            raise OperationsConflictError("Idempotency key was reused with changed return content")
        return _return_read(existing)
    line = await context.session.scalar(
        select(DeliveryReceiptLine)
        .where(
            DeliveryReceiptLine.organization_id == context.organization_id,
            DeliveryReceiptLine.id == receipt_line_id,
        )
        .with_for_update()
    )
    if line is None:
        raise OperationsNotFoundError("Receipt line not found")
    already_returned = await context.session.scalar(
        select(func.coalesce(func.sum(ReceiptReturn.quantity), 0)).where(
            ReceiptReturn.organization_id == context.organization_id,
            ReceiptReturn.receipt_line_id == line.id,
        )
    )
    if Decimal(str(already_returned or 0)) + payload.quantity > line.accepted_quantity:
        raise OperationsValidationError("Return quantity exceeds accepted quantity")
    returned = ReceiptReturn(
        organization_id=context.organization_id,
        receipt_line_id=line.id,
        quantity=payload.quantity,
        reason=payload.reason.strip(),
        idempotency_key=payload.idempotency_key,
        returned_at=payload.returned_at,
        created_by_user_id=context.user_id,
    )
    context.session.add(returned)
    receipt = await context.session.scalar(
        select(DeliveryReceipt)
        .where(
            DeliveryReceipt.organization_id == context.organization_id,
            DeliveryReceipt.id == line.receipt_id,
        )
        .with_for_update()
    )
    if receipt is None:
        raise OperationsConflictError("Receipt is missing")
    receipt.version += 1
    total_after = Decimal(str(already_returned or 0)) + payload.quantity
    receipt.status = (
        ReceiptStatus.FULLY_RETURNED
        if total_after == line.accepted_quantity
        else ReceiptStatus.RETURNED_IN_PART
    )
    po = await context.session.scalar(
        select(PurchaseOrder)
        .where(
            PurchaseOrder.organization_id == context.organization_id,
            PurchaseOrder.id == receipt.purchase_order_id,
        )
        .with_for_update()
    )
    if po is None:
        raise OperationsConflictError("Purchase order is missing")
    await context.session.flush()
    po.version += 1
    current = await _current_po_version(context, po)
    await _refresh_po_receipt_status(context, po, await _po_lines(context, current.id))
    _event(
        context,
        "delivery_return.recorded",
        "purchase_order",
        po.id,
        po.version,
        {"return_id": str(returned.id), "receipt_line_id": str(line.id)},
    )
    await context.session.flush()
    return _return_read(returned)


def _return_read(value: ReceiptReturn) -> ReturnRead:
    return ReturnRead(
        id=value.id,
        receipt_line_id=value.receipt_line_id,
        quantity=value.quantity,
        reason=value.reason,
        returned_at=value.returned_at,
        created_at=value.created_at,
    )


async def capture_invoice(
    context: RequestContext, purchase_order_id: uuid.UUID, payload: InvoiceCapture
) -> InvoiceRead:
    existing = await context.session.scalar(
        select(Invoice).where(
            Invoice.organization_id == context.organization_id,
            Invoice.capture_idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        if existing.purchase_order_id != purchase_order_id:
            raise OperationsConflictError("Idempotency key was used for another invoice")
        existing_read = await _invoice_read(context, existing)
        existing_lines = {
            (
                line.purchase_order_line_id,
                line.description,
                line.quantity,
                line.unit_price,
                line.tax_amount,
                line.freight_amount,
            )
            for line in existing_read.lines
        }
        requested_lines = {
            (
                line.purchase_order_line_id,
                line.description.strip(),
                line.quantity,
                line.unit_price,
                line.tax_amount,
                line.freight_amount,
            )
            for line in payload.lines
        }
        if (
            existing.supplier_invoice_number != payload.supplier_invoice_number
            or existing.invoice_date != payload.invoice_date
            or existing.currency != payload.currency
            or existing.subtotal != payload.subtotal
            or existing.tax_amount != payload.tax_amount
            or existing.freight_amount != payload.freight_amount
            or existing.total_amount != payload.total_amount
            or existing_lines != requested_lines
        ):
            raise OperationsConflictError("Idempotency key was reused with changed invoice content")
        return existing_read
    po = await context.session.scalar(
        select(PurchaseOrder)
        .where(
            PurchaseOrder.organization_id == context.organization_id,
            PurchaseOrder.id == purchase_order_id,
        )
        .with_for_update()
    )
    if po is None:
        raise OperationsNotFoundError("Purchase order not found")
    if po.status not in {
        PurchaseOrderStatus.ISSUED,
        PurchaseOrderStatus.ACKNOWLEDGED,
        PurchaseOrderStatus.PARTIALLY_RECEIVED,
        PurchaseOrderStatus.RECEIVED,
    }:
        raise OperationsConflictError("Purchase order is not open for invoices")
    current = await _current_po_version(context, po)
    line_by_id = {line.id: line for line in await _po_lines(context, current.id)}
    if any(item.purchase_order_line_id not in line_by_id for item in payload.lines):
        raise OperationsValidationError("Invoice lines must belong to the current PO version")
    normalized = normalized_invoice_number(payload.supplier_invoice_number)
    if not normalized:
        raise OperationsValidationError("Supplier invoice number must contain letters or digits")
    duplicate = bool(
        await context.session.scalar(
            select(Invoice.id).where(
                Invoice.organization_id == context.organization_id,
                Invoice.supplier_id == po.supplier_id,
                Invoice.normalized_invoice_number == normalized,
                Invoice.status != InvoiceStatus.VOIDED,
            )
        )
    )
    invoice = Invoice(
        organization_id=context.organization_id,
        purchase_order_id=po.id,
        supplier_id=po.supplier_id,
        supplier_invoice_number=payload.supplier_invoice_number,
        normalized_invoice_number=normalized,
        invoice_date=payload.invoice_date,
        currency=payload.currency,
        subtotal=payload.subtotal,
        tax_amount=payload.tax_amount,
        freight_amount=payload.freight_amount,
        total_amount=payload.total_amount,
        status=InvoiceStatus.DUPLICATE_SUSPECTED if duplicate else InvoiceStatus.CAPTURED,
        version=1,
        capture_idempotency_key=payload.idempotency_key,
        captured_by_user_id=context.user_id,
    )
    context.session.add(invoice)
    await context.session.flush()
    for line_number, item in enumerate(payload.lines, start=1):
        context.session.add(
            InvoiceLine(
                organization_id=context.organization_id,
                invoice_id=invoice.id,
                purchase_order_line_id=item.purchase_order_line_id,
                line_number=line_number,
                description=item.description.strip(),
                quantity=item.quantity,
                unit_price=item.unit_price,
                tax_amount=item.tax_amount,
                freight_amount=item.freight_amount,
                line_total=money(
                    item.quantity * item.unit_price + item.tax_amount + item.freight_amount
                ),
            )
        )
    _event(
        context,
        "invoice.captured",
        "invoice",
        invoice.id,
        invoice.version,
        {"purchase_order_id": str(po.id), "duplicate_suspected": duplicate},
    )
    await context.session.flush()
    return await _invoice_read(context, invoice)


async def _invoice_read(context: RequestContext, invoice: Invoice) -> InvoiceRead:
    await context.session.flush()
    await context.session.refresh(invoice)
    lines = list(
        await context.session.scalars(
            select(InvoiceLine)
            .where(
                InvoiceLine.organization_id == context.organization_id,
                InvoiceLine.invoice_id == invoice.id,
            )
            .order_by(InvoiceLine.line_number)
        )
    )
    return InvoiceRead(
        id=invoice.id,
        purchase_order_id=invoice.purchase_order_id,
        supplier_id=invoice.supplier_id,
        supplier_invoice_number=invoice.supplier_invoice_number,
        invoice_date=invoice.invoice_date,
        currency=invoice.currency,
        subtotal=invoice.subtotal,
        tax_amount=invoice.tax_amount,
        freight_amount=invoice.freight_amount,
        total_amount=invoice.total_amount,
        status=invoice.status,
        version=invoice.version,
        lines=[
            InvoiceLineRead(
                id=line.id,
                purchase_order_line_id=line.purchase_order_line_id,
                line_number=line.line_number,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                tax_amount=line.tax_amount,
                freight_amount=line.freight_amount,
                line_total=line.line_total,
            )
            for line in lines
        ],
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
    )


async def read_invoice(context: RequestContext, invoice_id: uuid.UUID) -> InvoiceRead:
    invoice = await context.session.scalar(
        select(Invoice).where(
            Invoice.organization_id == context.organization_id, Invoice.id == invoice_id
        )
    )
    if invoice is None:
        raise OperationsNotFoundError("Invoice not found")
    return await _invoice_read(context, invoice)


def _exception(
    kind: ExceptionKind,
    message: str,
    *,
    invoice_line_id: uuid.UUID | None = None,
    expected: object | None = None,
    actual: object | None = None,
    variance: Decimal | None = None,
) -> dict[str, object]:
    return {
        "kind": kind,
        "message": message,
        "invoice_line_id": invoice_line_id,
        "expected_value": str(expected) if expected is not None else None,
        "actual_value": str(actual) if actual is not None else None,
        "variance": variance,
    }


async def match_invoice(
    context: RequestContext, invoice_id: uuid.UUID, payload: InvoiceMatchCreate
) -> InvoiceMatchRead:
    existing = await context.session.scalar(
        select(InvoiceMatch).where(
            InvoiceMatch.organization_id == context.organization_id,
            InvoiceMatch.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        if existing.invoice_id != invoice_id:
            raise OperationsConflictError("Idempotency key was used for another invoice match")
        if (
            existing.mode is not payload.mode
            or existing.quantity_tolerance != payload.quantity_tolerance
            or existing.amount_tolerance != payload.amount_tolerance
            or existing.percent_tolerance != payload.percent_tolerance
        ):
            raise OperationsConflictError("Idempotency key was reused with changed match content")
        return await _match_read(context, existing)
    invoice = await context.session.scalar(
        select(Invoice)
        .where(Invoice.organization_id == context.organization_id, Invoice.id == invoice_id)
        .with_for_update()
    )
    if invoice is None:
        raise OperationsNotFoundError("Invoice not found")
    if invoice.version != payload.expected_invoice_version:
        raise OperationsConflictError("Invoice version is stale")
    if invoice.status in {
        InvoiceStatus.APPROVED_FOR_EXPORT,
        InvoiceStatus.EXPORTED,
        InvoiceStatus.VOIDED,
    }:
        raise OperationsConflictError("Invoice can no longer be matched")
    po = await context.session.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.organization_id == context.organization_id,
            PurchaseOrder.id == invoice.purchase_order_id,
        )
    )
    if po is None:
        raise OperationsConflictError("Purchase order is missing")
    po_version = await _current_po_version(context, po)
    po_lines = {line.id: line for line in await _po_lines(context, po_version.id)}
    invoice_lines = list(
        await context.session.scalars(
            select(InvoiceLine)
            .where(
                InvoiceLine.organization_id == context.organization_id,
                InvoiceLine.invoice_id == invoice.id,
            )
            .order_by(InvoiceLine.line_number)
        )
    )
    exceptions: list[dict[str, object]] = []
    duplicate_id = await context.session.scalar(
        select(Invoice.id).where(
            Invoice.organization_id == context.organization_id,
            Invoice.supplier_id == invoice.supplier_id,
            Invoice.normalized_invoice_number == invoice.normalized_invoice_number,
            Invoice.id != invoice.id,
            Invoice.status != InvoiceStatus.VOIDED,
        )
    )
    if duplicate_id is not None:
        exceptions.append(
            _exception(
                ExceptionKind.DUPLICATE_INVOICE,
                "Supplier invoice number duplicates another active invoice",
                expected="unique",
                actual=invoice.supplier_invoice_number,
            )
        )
    if invoice.currency != po.currency:
        exceptions.append(
            _exception(
                ExceptionKind.CURRENCY,
                "Invoice currency differs from purchase order",
                expected=po.currency,
                actual=invoice.currency,
            )
        )
    basis_quantities = await _match_basis_quantities(context, po, payload.mode.value)
    prior_billed = await _prior_billed_quantities(context, po.id, invoice.id)
    for line in invoice_lines:
        expected_line = po_lines.get(line.purchase_order_line_id)
        if expected_line is None:
            exceptions.append(
                _exception(
                    ExceptionKind.QUANTITY,
                    "Invoice line does not belong to the current PO version",
                    invoice_line_id=line.id,
                )
            )
            continue
        available = basis_quantities.get(expected_line.id, ZERO) - prior_billed.get(
            expected_line.id, ZERO
        )
        if line.quantity > available + payload.quantity_tolerance:
            exceptions.append(
                _exception(
                    ExceptionKind.QUANTITY,
                    "Invoice quantity exceeds the available matching quantity",
                    invoice_line_id=line.id,
                    expected=available,
                    actual=line.quantity,
                    variance=line.quantity - available,
                )
            )
        if not within_tolerance(
            line.unit_price,
            expected_line.unit_price,
            payload.amount_tolerance,
            payload.percent_tolerance,
        ):
            exceptions.append(
                _exception(
                    ExceptionKind.PRICE,
                    "Invoice unit price is outside tolerance",
                    invoice_line_id=line.id,
                    expected=expected_line.unit_price,
                    actual=line.unit_price,
                    variance=line.unit_price - expected_line.unit_price,
                )
            )
        expected_tax = money(expected_line.tax_amount * line.quantity / expected_line.quantity)
        expected_freight = money(
            expected_line.freight_amount * line.quantity / expected_line.quantity
        )
        for kind, actual, expected_value in (
            (ExceptionKind.TAX, line.tax_amount, expected_tax),
            (ExceptionKind.FREIGHT, line.freight_amount, expected_freight),
        ):
            if not within_tolerance(
                actual, expected_value, payload.amount_tolerance, payload.percent_tolerance
            ):
                exceptions.append(
                    _exception(
                        kind,
                        f"Invoice {kind.value} is outside tolerance",
                        invoice_line_id=line.id,
                        expected=expected_value,
                        actual=actual,
                        variance=actual - expected_value,
                    )
                )
    calculated_subtotal = money(
        sum((line.quantity * line.unit_price for line in invoice_lines), ZERO)
    )
    calculated_tax = money(sum((line.tax_amount for line in invoice_lines), ZERO))
    calculated_freight = money(sum((line.freight_amount for line in invoice_lines), ZERO))
    calculated_total = money(calculated_subtotal + calculated_tax + calculated_freight)
    for label, actual, expected_value in (
        ("subtotal", invoice.subtotal, calculated_subtotal),
        ("tax", invoice.tax_amount, calculated_tax),
        ("freight", invoice.freight_amount, calculated_freight),
        ("total", invoice.total_amount, calculated_total),
    ):
        if not within_tolerance(
            actual, expected_value, payload.amount_tolerance, payload.percent_tolerance
        ):
            exceptions.append(
                _exception(
                    ExceptionKind.TOTAL if label in {"subtotal", "total"} else ExceptionKind(label),
                    f"Invoice {label} does not reconcile to its lines",
                    expected=expected_value,
                    actual=actual,
                    variance=actual - expected_value,
                )
            )
    attempt = (
        await context.session.scalar(
            select(func.max(InvoiceMatch.attempt)).where(
                InvoiceMatch.organization_id == context.organization_id,
                InvoiceMatch.invoice_id == invoice.id,
            )
        )
        or 0
    ) + 1
    input_snapshot: dict[str, object] = {
        "invoice_id": str(invoice.id),
        "invoice_version": invoice.version,
        "purchase_order_id": str(po.id),
        "purchase_order_revision": po.current_revision,
        "purchase_order_digest": po.content_digest,
        "mode": payload.mode.value,
        "tolerances": {
            "quantity": str(payload.quantity_tolerance),
            "amount": str(payload.amount_tolerance),
            "percent": str(payload.percent_tolerance),
        },
        "basis_quantities": {str(key): str(value) for key, value in basis_quantities.items()},
        "prior_billed": {str(key): str(value) for key, value in prior_billed.items()},
        "invoice_lines": [
            {
                "id": str(line.id),
                "po_line_id": str(line.purchase_order_line_id),
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "tax_amount": str(line.tax_amount),
                "freight_amount": str(line.freight_amount),
            }
            for line in invoice_lines
        ],
    }
    outcome = MatchOutcome.MISMATCH if exceptions else MatchOutcome.MATCHED
    match = InvoiceMatch(
        organization_id=context.organization_id,
        invoice_id=invoice.id,
        attempt=attempt,
        mode=payload.mode,
        outcome=outcome,
        idempotency_key=payload.idempotency_key,
        input_digest=digest(input_snapshot),
        quantity_tolerance=payload.quantity_tolerance,
        amount_tolerance=payload.amount_tolerance,
        percent_tolerance=payload.percent_tolerance,
        snapshot=input_snapshot,
        matched_by_user_id=context.user_id,
    )
    context.session.add(match)
    await context.session.flush()
    for item in exceptions:
        context.session.add(
            MatchException(
                organization_id=context.organization_id,
                match_id=match.id,
                invoice_line_id=cast(uuid.UUID | None, item["invoice_line_id"]),
                kind=cast(ExceptionKind, item["kind"]),
                blocking=True,
                message=str(item["message"]),
                expected_value=cast(str | None, item["expected_value"]),
                actual_value=cast(str | None, item["actual_value"]),
                variance=cast(Decimal | None, item["variance"]),
            )
        )
    invoice.status = InvoiceStatus.MISMATCH if exceptions else InvoiceStatus.MATCHED
    invoice.version += 1
    _event(
        context,
        "invoice.matched" if not exceptions else "invoice.match_failed",
        "invoice",
        invoice.id,
        invoice.version,
        {"match_id": str(match.id), "exception_count": len(exceptions), "mode": payload.mode.value},
    )
    await context.session.flush()
    return await _match_read(context, match)


async def _match_basis_quantities(
    context: RequestContext, po: PurchaseOrder, mode: str
) -> dict[uuid.UUID, Decimal]:
    current = await _current_po_version(context, po)
    lines = await _po_lines(context, current.id)
    if mode == "two_way":
        return {line.id: line.quantity for line in lines}
    accepted_rows = (
        await context.session.execute(
            select(
                DeliveryReceiptLine.purchase_order_line_id,
                func.coalesce(func.sum(DeliveryReceiptLine.accepted_quantity), 0),
            )
            .join(
                DeliveryReceipt,
                (DeliveryReceipt.organization_id == DeliveryReceiptLine.organization_id)
                & (DeliveryReceipt.id == DeliveryReceiptLine.receipt_id),
            )
            .where(
                DeliveryReceiptLine.organization_id == context.organization_id,
                DeliveryReceipt.purchase_order_id == po.id,
            )
            .group_by(DeliveryReceiptLine.purchase_order_line_id)
        )
    ).all()
    result = {key: Decimal(str(value)) for key, value in accepted_rows}
    returned_rows = (
        await context.session.execute(
            select(
                DeliveryReceiptLine.purchase_order_line_id,
                func.coalesce(func.sum(ReceiptReturn.quantity), 0),
            )
            .join(
                ReceiptReturn,
                (ReceiptReturn.organization_id == DeliveryReceiptLine.organization_id)
                & (ReceiptReturn.receipt_line_id == DeliveryReceiptLine.id),
            )
            .join(
                DeliveryReceipt,
                (DeliveryReceipt.organization_id == DeliveryReceiptLine.organization_id)
                & (DeliveryReceipt.id == DeliveryReceiptLine.receipt_id),
            )
            .where(
                DeliveryReceiptLine.organization_id == context.organization_id,
                DeliveryReceipt.purchase_order_id == po.id,
            )
            .group_by(DeliveryReceiptLine.purchase_order_line_id)
        )
    ).all()
    for key, value in returned_rows:
        result[key] = result.get(key, ZERO) - Decimal(str(value))
    return result


async def _prior_billed_quantities(
    context: RequestContext, po_id: uuid.UUID, excluded_invoice_id: uuid.UUID
) -> dict[uuid.UUID, Decimal]:
    rows = (
        await context.session.execute(
            select(
                InvoiceLine.purchase_order_line_id,
                func.coalesce(func.sum(InvoiceLine.quantity), 0),
            )
            .join(
                Invoice,
                (Invoice.organization_id == InvoiceLine.organization_id)
                & (Invoice.id == InvoiceLine.invoice_id),
            )
            .where(
                InvoiceLine.organization_id == context.organization_id,
                Invoice.purchase_order_id == po_id,
                Invoice.id != excluded_invoice_id,
                Invoice.status.in_(
                    [
                        InvoiceStatus.MATCHED,
                        InvoiceStatus.APPROVED_FOR_EXPORT,
                        InvoiceStatus.EXPORTED,
                    ]
                ),
            )
            .group_by(InvoiceLine.purchase_order_line_id)
        )
    ).all()
    return {key: Decimal(str(value)) for key, value in rows}


async def _match_read(context: RequestContext, match: InvoiceMatch) -> InvoiceMatchRead:
    exceptions = list(
        await context.session.scalars(
            select(MatchException)
            .where(
                MatchException.organization_id == context.organization_id,
                MatchException.match_id == match.id,
            )
            .order_by(MatchException.created_at, MatchException.id)
        )
    )
    return InvoiceMatchRead(
        id=match.id,
        invoice_id=match.invoice_id,
        attempt=match.attempt,
        mode=match.mode,
        outcome=match.outcome,
        input_digest=match.input_digest,
        quantity_tolerance=match.quantity_tolerance,
        amount_tolerance=match.amount_tolerance,
        percent_tolerance=match.percent_tolerance,
        snapshot=match.snapshot,
        exceptions=[
            MatchExceptionRead(
                id=item.id,
                invoice_line_id=item.invoice_line_id,
                kind=item.kind,
                blocking=item.blocking,
                message=item.message,
                expected_value=item.expected_value,
                actual_value=item.actual_value,
                variance=item.variance,
                resolved_at=item.resolved_at,
                resolution=item.resolution,
            )
            for item in exceptions
        ],
        created_at=match.created_at,
    )


async def resolve_match_exception(
    context: RequestContext, exception_id: uuid.UUID, payload: ExceptionResolve
) -> InvoiceMatchRead:
    exception = await context.session.scalar(
        select(MatchException)
        .where(
            MatchException.organization_id == context.organization_id,
            MatchException.id == exception_id,
        )
        .with_for_update()
    )
    if exception is None:
        raise OperationsNotFoundError("Match exception not found")
    match = await context.session.scalar(
        select(InvoiceMatch).where(
            InvoiceMatch.organization_id == context.organization_id,
            InvoiceMatch.id == exception.match_id,
        )
    )
    if match is None:
        raise OperationsConflictError("Invoice match is missing")
    invoice = await context.session.scalar(
        select(Invoice)
        .where(
            Invoice.organization_id == context.organization_id,
            Invoice.id == match.invoice_id,
        )
        .with_for_update()
    )
    if invoice is None:
        raise OperationsConflictError("Invoice is missing")
    if invoice.version != payload.expected_invoice_version:
        raise OperationsConflictError("Invoice version is stale")
    if exception.resolved_at is not None:
        raise OperationsConflictError("Match exception is already resolved")
    exception.resolved_at = datetime.now(UTC)
    exception.resolved_by_user_id = context.user_id
    exception.resolution = payload.resolution.strip()
    invoice.version += 1
    _event(
        context,
        "invoice.match_exception_resolved",
        "invoice",
        invoice.id,
        invoice.version,
        {"exception_id": str(exception.id), "match_id": str(match.id)},
    )
    return await _match_read(context, match)


async def approve_invoice_for_export(
    context: RequestContext, invoice_id: uuid.UUID, payload: InvoiceApprove
) -> InvoiceRead:
    invoice = await context.session.scalar(
        select(Invoice)
        .where(Invoice.organization_id == context.organization_id, Invoice.id == invoice_id)
        .with_for_update()
    )
    if invoice is None:
        raise OperationsNotFoundError("Invoice not found")
    if invoice.version != payload.expected_invoice_version:
        raise OperationsConflictError("Invoice version is stale")
    if invoice.status not in {InvoiceStatus.MATCHED, InvoiceStatus.MISMATCH}:
        raise OperationsConflictError("Invoice must be matched before export approval")
    latest = await context.session.scalar(
        select(InvoiceMatch)
        .where(
            InvoiceMatch.organization_id == context.organization_id,
            InvoiceMatch.invoice_id == invoice.id,
        )
        .order_by(InvoiceMatch.attempt.desc())
        .limit(1)
    )
    if latest is None:
        raise OperationsValidationError("Invoice has no match result")
    unresolved = await context.session.scalar(
        select(func.count(MatchException.id)).where(
            MatchException.organization_id == context.organization_id,
            MatchException.match_id == latest.id,
            MatchException.blocking.is_(True),
            MatchException.resolved_at.is_(None),
        )
    )
    if unresolved:
        raise OperationsValidationError("All blocking match exceptions must be resolved")
    invoice.status = InvoiceStatus.APPROVED_FOR_EXPORT
    invoice.version += 1
    _event(
        context,
        "invoice.approved_for_export",
        "invoice",
        invoice.id,
        invoice.version,
        {"match_id": str(latest.id)},
    )
    return await _invoice_read(context, invoice)


async def export_invoice(
    context: RequestContext, invoice_id: uuid.UUID, payload: AccountingExportCreate
) -> AccountingExportRead:
    existing_by_key = await context.session.scalar(
        select(AccountingExport).where(
            AccountingExport.organization_id == context.organization_id,
            AccountingExport.idempotency_key == payload.idempotency_key,
        )
    )
    if existing_by_key is not None:
        if existing_by_key.invoice_id != invoice_id:
            raise OperationsConflictError("Idempotency key was used for another export")
        return await _export_read(context, existing_by_key)
    existing_invoice = await context.session.scalar(
        select(AccountingExport).where(
            AccountingExport.organization_id == context.organization_id,
            AccountingExport.invoice_id == invoice_id,
        )
    )
    if existing_invoice is not None:
        return await _export_read(context, existing_invoice)
    invoice = await context.session.scalar(
        select(Invoice)
        .where(Invoice.organization_id == context.organization_id, Invoice.id == invoice_id)
        .with_for_update()
    )
    if invoice is None:
        raise OperationsNotFoundError("Invoice not found")
    if invoice.version != payload.expected_invoice_version:
        raise OperationsConflictError("Invoice version is stale")
    if invoice.status is not InvoiceStatus.APPROVED_FOR_EXPORT:
        raise OperationsValidationError("Invoice is not approved for accounting export")
    lines = list(
        await context.session.scalars(
            select(InvoiceLine)
            .where(
                InvoiceLine.organization_id == context.organization_id,
                InvoiceLine.invoice_id == invoice.id,
            )
            .order_by(InvoiceLine.line_number)
        )
    )
    external_reference = f"PX-INVOICE-{invoice.id}"
    export_payload: dict[str, object] = {
        "external_reference": external_reference,
        "invoice_id": str(invoice.id),
        "supplier_id": str(invoice.supplier_id),
        "supplier_invoice_number": invoice.supplier_invoice_number,
        "invoice_date": invoice.invoice_date.isoformat(),
        "currency": invoice.currency,
        "subtotal": str(invoice.subtotal),
        "tax_amount": str(invoice.tax_amount),
        "freight_amount": str(invoice.freight_amount),
        "total_amount": str(invoice.total_amount),
        "lines": [
            {
                "line_number": line.line_number,
                "description": line.description,
                "quantity": str(line.quantity),
                "unit_price": str(line.unit_price),
                "tax_amount": str(line.tax_amount),
                "freight_amount": str(line.freight_amount),
                "line_total": str(line.line_total),
            }
            for line in lines
        ],
    }
    payload_digest = digest(export_payload)
    export = AccountingExport(
        organization_id=context.organization_id,
        invoice_id=invoice.id,
        provider="sandbox",
        external_reference=external_reference,
        idempotency_key=payload.idempotency_key,
        payload=export_payload,
        payload_digest=payload_digest,
        status=AccountingExportStatus.PENDING,
        reconciliation_status=ReconciliationStatus.PENDING,
        version=1,
        attempt_count=0,
        created_by_user_id=context.user_id,
    )
    context.session.add(export)
    await context.session.flush()
    await _deliver_sandbox_export(context, export, invoice)
    return await _export_read(context, export)


async def _deliver_sandbox_export(
    context: RequestContext, export: AccountingExport, invoice: Invoice
) -> None:
    export.attempt_count += 1
    existing = await context.session.scalar(
        select(AccountingSandboxEntry).where(
            AccountingSandboxEntry.organization_id == context.organization_id,
            AccountingSandboxEntry.external_reference == export.external_reference,
        )
    )
    if existing is not None:
        if existing.payload_digest != export.payload_digest:
            export.status = AccountingExportStatus.RECONCILIATION_REQUIRED
            export.reconciliation_status = ReconciliationStatus.MISMATCH
            export.last_error = "Stable external reference exists with a different payload"
            export.version += 1
            _event(
                context,
                "accounting_export.reconciliation_required",
                "accounting_export",
                export.id,
                export.version,
                {"external_reference": export.external_reference},
            )
            return
        external_id = existing.external_id
    else:
        external_id = f"SBX-{uuid.uuid4()}"
        context.session.add(
            AccountingSandboxEntry(
                organization_id=context.organization_id,
                export_id=export.id,
                external_reference=export.external_reference,
                external_id=external_id,
                payload_digest=export.payload_digest,
                payload=export.payload,
            )
        )
    now = datetime.now(UTC)
    export.external_id = external_id
    export.status = AccountingExportStatus.SUCCEEDED
    export.exported_at = now
    export.last_error = None
    export.version += 1
    invoice.status = InvoiceStatus.EXPORTED
    invoice.version += 1
    _event(
        context,
        "accounting_export.succeeded",
        "accounting_export",
        export.id,
        export.version,
        {"external_reference": export.external_reference, "external_id": external_id},
    )
    _event(
        context,
        "invoice.exported",
        "invoice",
        invoice.id,
        invoice.version,
        {"accounting_export_id": str(export.id), "external_reference": export.external_reference},
    )
    await context.session.flush()


async def retry_accounting_export(
    context: RequestContext, export_id: uuid.UUID, payload: AccountingExportRetry
) -> AccountingExportRead:
    export = await context.session.scalar(
        select(AccountingExport)
        .where(
            AccountingExport.organization_id == context.organization_id,
            AccountingExport.id == export_id,
        )
        .with_for_update()
    )
    if export is None:
        raise OperationsNotFoundError("Accounting export not found")
    if export.version != payload.expected_version:
        raise OperationsConflictError("Accounting export version is stale")
    if export.status in {AccountingExportStatus.SUCCEEDED, AccountingExportStatus.RECONCILED}:
        return await _export_read(context, export)
    invoice = await context.session.scalar(
        select(Invoice)
        .where(
            Invoice.organization_id == context.organization_id,
            Invoice.id == export.invoice_id,
        )
        .with_for_update()
    )
    if invoice is None:
        raise OperationsConflictError("Invoice is missing")
    await _deliver_sandbox_export(context, export, invoice)
    return await _export_read(context, export)


async def reconcile_accounting_export(
    context: RequestContext, export_id: uuid.UUID, payload: AccountingReconcile
) -> AccountingExportRead:
    export = await context.session.scalar(
        select(AccountingExport)
        .where(
            AccountingExport.organization_id == context.organization_id,
            AccountingExport.id == export_id,
        )
        .with_for_update()
    )
    if export is None:
        raise OperationsNotFoundError("Accounting export not found")
    if export.version != payload.expected_version:
        raise OperationsConflictError("Accounting export version is stale")
    if export.external_id is None:
        raise OperationsValidationError("Accounting export has not reached the sandbox")
    export.reconciliation_status = payload.status
    export.version += 1
    if payload.status is ReconciliationStatus.RECONCILED:
        export.status = AccountingExportStatus.RECONCILED
        export.reconciled_at = datetime.now(UTC)
        export.last_error = None
    else:
        export.status = AccountingExportStatus.RECONCILIATION_REQUIRED
        export.last_error = payload.note or "Accounting reconciliation mismatch"
    _event(
        context,
        f"accounting_export.{payload.status.value}",
        "accounting_export",
        export.id,
        export.version,
        {"external_reference": export.external_reference, "note": payload.note},
    )
    return await _export_read(context, export)


async def _export_read(context: RequestContext, export: AccountingExport) -> AccountingExportRead:
    await context.session.flush()
    await context.session.refresh(export)
    return AccountingExportRead(
        id=export.id,
        invoice_id=export.invoice_id,
        provider=export.provider,
        external_reference=export.external_reference,
        external_id=export.external_id,
        payload_digest=export.payload_digest,
        status=export.status,
        reconciliation_status=export.reconciliation_status,
        version=export.version,
        attempt_count=export.attempt_count,
        last_error=export.last_error,
        exported_at=export.exported_at,
        reconciled_at=export.reconciled_at,
        created_at=export.created_at,
        updated_at=export.updated_at,
    )
