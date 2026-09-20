from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.auth.context import RequestContext, get_request_context
from app.main import app
from app.models.operations import ReceiptStatus, ReconciliationStatus
from app.schemas.operations import (
    AccountingReconcile,
    InvoiceCapture,
    PurchaseOrderAmend,
    ReceiptCreate,
)
from app.services.operations import (
    digest,
    normalized_invoice_number,
    receipt_return_status,
    within_tolerance,
)


def test_invoice_number_normalization_supports_duplicate_detection() -> None:
    assert normalized_invoice_number(" inv-2026 / 0042 ") == "INV20260042"


def test_matching_tolerance_uses_larger_absolute_or_percentage_limit() -> None:
    assert within_tolerance(Decimal("101.00"), Decimal("100"), Decimal("0.01"), Decimal("1"))
    assert not within_tolerance(Decimal("101.01"), Decimal("100"), Decimal("0.01"), Decimal("1"))
    assert within_tolerance(Decimal("10.01"), Decimal("10"), Decimal("0.01"), Decimal("0"))


def test_matching_digest_is_deterministic() -> None:
    assert digest({"invoice": "1", "lines": [1, 2]}) == digest({"lines": [1, 2], "invoice": "1"})


def test_receipt_is_fully_returned_only_when_all_accepted_goods_are_returned() -> None:
    assert receipt_return_status(Decimal("5"), Decimal("2")) is ReceiptStatus.RETURNED_IN_PART
    assert receipt_return_status(Decimal("5"), Decimal("5")) is ReceiptStatus.FULLY_RETURNED


def test_receipt_rejects_empty_delivered_quantity() -> None:
    with pytest.raises(ValidationError, match="accepted or rejected"):
        ReceiptCreate(
            expected_po_version=1,
            idempotency_key="receipt-0001",
            received_at=datetime.now(UTC),
            lines=[
                {
                    "purchase_order_line_id": uuid4(),
                    "accepted_quantity": "0",
                    "rejected_quantity": "0",
                }
            ],
        )


def test_receipt_requires_timezone() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        ReceiptCreate(
            expected_po_version=1,
            idempotency_key="receipt-0001",
            received_at=datetime(2026, 9, 20, 12, 0),
            lines=[
                {
                    "purchase_order_line_id": uuid4(),
                    "accepted_quantity": "1",
                    "rejected_quantity": "0",
                }
            ],
        )


def test_amendment_requires_each_source_line_once() -> None:
    source = uuid4()
    line = {
        "source_line_id": source,
        "description": "Laptop",
        "quantity": "1",
        "unit": "each",
        "unit_price": "100",
    }
    with pytest.raises(ValidationError, match="unique"):
        PurchaseOrderAmend(
            expected_version=1,
            expected_content_digest="a" * 64,
            reason="Commercial update",
            lines=[line, line],
        )


def test_invoice_rejects_duplicate_po_lines() -> None:
    line_id = uuid4()
    line = {
        "purchase_order_line_id": line_id,
        "description": "Laptop",
        "quantity": "1",
        "unit_price": "100",
    }
    with pytest.raises(ValidationError, match="unique"):
        InvoiceCapture(
            supplier_invoice_number="INV-1",
            invoice_date="2026-09-20",
            currency="PKR",
            subtotal="200",
            tax_amount="0",
            freight_amount="0",
            total_amount="200",
            idempotency_key="invoice-0001",
            lines=[line, line],
        )


def test_reconciliation_cannot_be_reset_to_pending() -> None:
    with pytest.raises(ValidationError, match="reconciled or mismatch"):
        AccountingReconcile(expected_version=1, status=ReconciliationStatus.PENDING)


def test_order_command_requires_explicit_permission() -> None:
    async def unauthorized_context():  # type: ignore[no-untyped-def]
        yield RequestContext(
            organization_id=uuid4(),
            user_id=uuid4(),
            membership_id=uuid4(),
            permissions=frozenset(),
            session=AsyncMock(),
        )

    app.dependency_overrides[get_request_context] = unauthorized_context
    try:
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/awards/{uuid4()}/purchase-orders",
                json={
                    "supplier_id": str(uuid4()),
                    "expected_award_digest": "a" * 64,
                    "idempotency_key": "po-unauthorized-0001",
                },
            )
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "permission_denied"
    finally:
        app.dependency_overrides.clear()
