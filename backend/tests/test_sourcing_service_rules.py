from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models.sourcing import Rfq, RfqInvitation, RfqStatus
from app.services.sourcing import (
    SourcingConflictError,
    SourcingValidationError,
    _require_current_revision,
    _require_open_invitation_response,
)


def rfq_with(*, status: RfqStatus, deadline: datetime) -> Rfq:
    return Rfq(
        organization_id=uuid4(),
        requisition_id=uuid4(),
        title="Laptop procurement",
        currency="PKR",
        submission_deadline=deadline,
        status=status,
    )


def test_invitation_response_requires_published_rfq() -> None:
    rfq = rfq_with(status=RfqStatus.DRAFT, deadline=datetime.now(UTC) + timedelta(days=1))
    with pytest.raises(SourcingConflictError, match="not accepting"):
        _require_open_invitation_response(rfq)


def test_invitation_response_rejects_elapsed_deadline() -> None:
    rfq = rfq_with(status=RfqStatus.PUBLISHED, deadline=datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(SourcingValidationError, match="deadline has passed"):
        _require_open_invitation_response(rfq)


def test_submission_rejects_stale_rfq_revision() -> None:
    current_revision_id = uuid4()
    invitation = RfqInvitation(rfq_revision_id=current_revision_id)
    with pytest.raises(SourcingConflictError, match="RFQ was amended"):
        _require_current_revision(invitation, uuid4())


def test_submission_accepts_current_rfq_revision() -> None:
    current_revision_id = uuid4()
    invitation = RfqInvitation(rfq_revision_id=current_revision_id)
    _require_current_revision(invitation, current_revision_id)
