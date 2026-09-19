from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.sourcing import ClarificationVisibility
from app.schemas.sourcing import (
    ClarificationCreate,
    InvitationCreate,
    InvitationNoBid,
    RfqCreate,
    SubmissionCreate,
)


def test_rfq_requires_timezone_aware_deadline() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        RfqCreate(
            requisition_id=uuid4(),
            title="Laptop procurement",
            submission_deadline=datetime(2026, 10, 1, 17, 0),
        )


def test_rfq_normalizes_title() -> None:
    payload = RfqCreate(
        requisition_id=uuid4(),
        title="  Laptop procurement  ",
        submission_deadline=datetime.now(UTC) + timedelta(days=7),
    )
    assert payload.title == "Laptop procurement"


def test_invitation_rejects_duplicate_suppliers() -> None:
    supplier_id = uuid4()
    with pytest.raises(ValidationError, match="supplier_ids must be unique"):
        InvitationCreate(supplier_ids=[supplier_id, supplier_id])


def test_no_bid_requires_a_meaningful_reason() -> None:
    with pytest.raises(ValidationError, match="at least 2 characters"):
        InvitationNoBid(expected_rfq_version=2, reason=" x ")


def test_no_bid_normalizes_reason() -> None:
    payload = InvitationNoBid(expected_rfq_version=2, reason="  Capacity unavailable  ")
    assert payload.reason == "Capacity unavailable"


def test_submission_rejects_duplicate_rfq_items() -> None:
    item_id = uuid4()
    line = {
        "rfq_item_id": item_id,
        "quantity": Decimal("10"),
        "unit_price": Decimal("100.00"),
    }
    with pytest.raises(ValidationError, match="only once"):
        SubmissionCreate(
            rfq_revision_id=uuid4(),
            currency="PKR",
            valid_until=date.today() + timedelta(days=30),
            delivery_terms="Delivery within fourteen days",
            lines=[line, line],
        )


def test_submission_rejects_duplicate_document_versions() -> None:
    document_version_id = uuid4()
    with pytest.raises(ValidationError, match="document version"):
        SubmissionCreate(
            rfq_revision_id=uuid4(),
            currency="PKR",
            valid_until=date.today() + timedelta(days=30),
            delivery_terms="Delivery within fourteen days",
            document_version_ids=[document_version_id, document_version_id],
            lines=[
                {
                    "rfq_item_id": uuid4(),
                    "quantity": Decimal("10"),
                    "unit_price": Decimal("100.00"),
                }
            ],
        )


def test_private_clarification_requires_invitation() -> None:
    with pytest.raises(ValidationError, match="require invitation_id"):
        ClarificationCreate(
            visibility=ClarificationVisibility.PRIVATE,
            question="Can the delivery schedule be split?",
        )


def test_shared_clarification_can_address_all_bidders() -> None:
    payload = ClarificationCreate(
        visibility=ClarificationVisibility.SHARED,
        question="  Is equivalent equipment acceptable?  ",
    )
    assert payload.question == "Is equivalent equipment acceptable?"
