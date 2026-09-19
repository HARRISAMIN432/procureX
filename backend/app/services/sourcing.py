import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.auth.context import RequestContext
from app.models.platform import ActorType, AuditEvent, OutboxEvent
from app.models.requisitions import (
    Requisition,
    RequisitionLine,
    RequisitionRequirement,
    RequisitionStatus,
)
from app.models.sourcing import (
    ClarificationStatus,
    InvitationStatus,
    QuoteLine,
    QuoteSubmission,
    Rfq,
    RfqClarification,
    RfqInvitation,
    RfqItem,
    RfqRequirement,
    RfqRevision,
    RfqStatus,
    SubmissionStatus,
)
from app.models.suppliers import Supplier, SupplierStatus
from app.schemas.sourcing import (
    ClarificationAnswer,
    ClarificationCreate,
    ClarificationRead,
    InvitationAcknowledge,
    InvitationCreate,
    InvitationNoBid,
    InvitationRead,
    RfqAmend,
    RfqCancel,
    RfqCreate,
    RfqItemRead,
    RfqList,
    RfqRead,
    RfqReplace,
    RfqRequirementRead,
    RfqTransition,
    SubmissionCreate,
    SubmissionLineRead,
    SubmissionRead,
    SubmissionWithdraw,
)


class SourcingNotFoundError(ValueError):
    pass


class SourcingConflictError(ValueError):
    pass


class SourcingValidationError(ValueError):
    pass


async def _locked_rfq(context: RequestContext, rfq_id: uuid.UUID) -> Rfq:
    rfq = await context.session.scalar(
        select(Rfq)
        .where(Rfq.organization_id == context.organization_id, Rfq.id == rfq_id)
        .with_for_update()
    )
    if rfq is None:
        raise SourcingNotFoundError("RFQ not found")
    return rfq


def _check_version(rfq: Rfq, expected_version: int) -> None:
    if rfq.version != expected_version:
        raise SourcingConflictError(
            f"Expected version {expected_version}, current version is {rfq.version}"
        )


def _require_future_deadline(deadline: datetime) -> None:
    if deadline.astimezone(UTC) <= datetime.now(UTC):
        raise SourcingValidationError("Submission deadline must be in the future")


def _record_change(
    context: RequestContext, rfq: Rfq, action: str, changes: dict[str, object]
) -> None:
    context.session.add_all(
        [
            AuditEvent(
                organization_id=context.organization_id,
                actor_type=ActorType.USER,
                actor_id=context.user_id,
                action=action,
                object_type="rfq",
                object_id=rfq.id,
                object_version=rfq.version,
                changes=changes,
            ),
            OutboxEvent(
                organization_id=context.organization_id,
                aggregate_type="rfq",
                aggregate_id=rfq.id,
                aggregate_version=rfq.version,
                event_type=action,
                schema_version=1,
                payload={
                    "rfq_id": str(rfq.id),
                    "version": rfq.version,
                    "status": rfq.status.value,
                    **changes,
                },
                actor_id=context.user_id,
            ),
        ]
    )


async def create_rfq(context: RequestContext, payload: RfqCreate) -> RfqRead:
    _require_future_deadline(payload.submission_deadline)
    requisition = await context.session.scalar(
        select(Requisition)
        .where(
            Requisition.organization_id == context.organization_id,
            Requisition.id == payload.requisition_id,
        )
        .with_for_update()
    )
    if requisition is None:
        raise SourcingNotFoundError("Requisition not found")
    if requisition.status is not RequisitionStatus.APPROVED:
        raise SourcingConflictError("Only an approved requisition can create an RFQ")
    existing = await context.session.scalar(
        select(Rfq.id).where(
            Rfq.organization_id == context.organization_id,
            Rfq.requisition_id == requisition.id,
        )
    )
    if existing is not None:
        raise SourcingConflictError("An RFQ already exists for this requisition")

    lines = list(
        await context.session.scalars(
            select(RequisitionLine).where(
                RequisitionLine.organization_id == context.organization_id,
                RequisitionLine.requisition_id == requisition.id,
            )
        )
    )
    requirements = list(
        await context.session.scalars(
            select(RequisitionRequirement).where(
                RequisitionRequirement.organization_id == context.organization_id,
                RequisitionRequirement.requisition_id == requisition.id,
            )
        )
    )
    if not lines:
        raise SourcingValidationError("The approved requisition has no line items")

    rfq = Rfq(
        id=uuid.uuid4(),
        organization_id=context.organization_id,
        requisition_id=requisition.id,
        title=payload.title,
        currency=requisition.currency,
        submission_deadline=payload.submission_deadline,
        terms=payload.terms,
        status=RfqStatus.DRAFT,
        version=1,
        created_by_user_id=context.user_id,
    )
    context.session.add(rfq)
    await context.session.flush()
    item_ids = {line.id: uuid.uuid4() for line in lines}
    context.session.add_all(
        [
            RfqItem(
                id=item_ids[line.id],
                organization_id=context.organization_id,
                rfq_id=rfq.id,
                requisition_line_id=line.id,
                line_number=line.line_number,
                description=line.description,
                quantity=line.quantity,
                unit=line.unit,
                category=line.category,
                specifications=line.specifications,
                alternatives_allowed=line.alternatives_allowed,
            )
            for line in lines
        ]
    )
    context.session.add_all(
        [
            RfqRequirement(
                organization_id=context.organization_id,
                rfq_id=rfq.id,
                item_id=(
                    item_ids[requirement.line_id] if requirement.line_id is not None else None
                ),
                requisition_requirement_id=requirement.id,
                priority=requirement.priority.value,
                criterion=requirement.criterion,
                verification_method=requirement.verification_method,
            )
            for requirement in requirements
        ]
    )
    _record_change(context, rfq, "rfq.created", {"requisition_id": str(requisition.id)})
    await context.session.flush()
    return await read_rfq(context, rfq.id)


async def replace_rfq(context: RequestContext, rfq_id: uuid.UUID, payload: RfqReplace) -> RfqRead:
    _require_future_deadline(payload.submission_deadline)
    rfq = await _locked_rfq(context, rfq_id)
    _check_version(rfq, payload.expected_version)
    if rfq.status is not RfqStatus.DRAFT:
        raise SourcingConflictError("Only a draft RFQ can be edited")
    rfq.title = payload.title
    rfq.submission_deadline = payload.submission_deadline
    rfq.terms = payload.terms
    rfq.version += 1
    _record_change(context, rfq, "rfq.updated", {})
    await context.session.flush()
    return await read_rfq(context, rfq.id)


async def invite_suppliers(
    context: RequestContext, rfq_id: uuid.UUID, payload: InvitationCreate
) -> RfqRead:
    rfq = await _locked_rfq(context, rfq_id)
    if rfq.status is not RfqStatus.DRAFT:
        raise SourcingConflictError("Suppliers can only be added before publication")
    suppliers = list(
        await context.session.scalars(
            select(Supplier).where(
                Supplier.organization_id == context.organization_id,
                Supplier.id.in_(payload.supplier_ids),
            )
        )
    )
    if len(suppliers) != len(payload.supplier_ids):
        raise SourcingNotFoundError("One or more suppliers were not found")
    if any(supplier.status is not SupplierStatus.APPROVED for supplier in suppliers):
        raise SourcingValidationError("Only approved suppliers can be invited")
    existing = set(
        await context.session.scalars(
            select(RfqInvitation.supplier_id).where(
                RfqInvitation.organization_id == context.organization_id,
                RfqInvitation.rfq_id == rfq.id,
                RfqInvitation.supplier_id.in_(payload.supplier_ids),
            )
        )
    )
    if existing:
        raise SourcingConflictError("One or more suppliers are already invited")
    context.session.add_all(
        [
            RfqInvitation(
                organization_id=context.organization_id,
                rfq_id=rfq.id,
                supplier_id=supplier_id,
                status=InvitationStatus.INVITED,
            )
            for supplier_id in payload.supplier_ids
        ]
    )
    rfq.version += 1
    _record_change(
        context,
        rfq,
        "rfq.suppliers_added",
        {"supplier_ids": [str(item) for item in payload.supplier_ids]},
    )
    await context.session.flush()
    return await read_rfq(context, rfq.id)


async def _locked_invitation_and_rfq(
    context: RequestContext, invitation_id: uuid.UUID, expected_rfq_version: int
) -> tuple[RfqInvitation, Rfq]:
    candidate = await context.session.scalar(
        select(RfqInvitation).where(
            RfqInvitation.organization_id == context.organization_id,
            RfqInvitation.id == invitation_id,
        )
    )
    if candidate is None:
        raise SourcingNotFoundError("Invitation not found")
    rfq = await _locked_rfq(context, candidate.rfq_id)
    _check_version(rfq, expected_rfq_version)
    invitation = await context.session.scalar(
        select(RfqInvitation)
        .where(
            RfqInvitation.organization_id == context.organization_id,
            RfqInvitation.rfq_id == rfq.id,
            RfqInvitation.id == invitation_id,
        )
        .with_for_update()
    )
    if invitation is None:
        raise SourcingNotFoundError("Invitation not found")
    return invitation, rfq


def _require_open_invitation_response(rfq: Rfq) -> datetime:
    if rfq.status is not RfqStatus.PUBLISHED:
        raise SourcingConflictError("The RFQ is not accepting invitation responses")
    now = datetime.now(UTC)
    if now > rfq.submission_deadline.astimezone(UTC):
        raise SourcingValidationError("The submission deadline has passed")
    return now


def _require_current_revision(
    invitation: RfqInvitation, submitted_revision_id: uuid.UUID
) -> None:
    if invitation.rfq_revision_id is None:
        raise SourcingConflictError("Invitation has no published RFQ revision")
    if submitted_revision_id != invitation.rfq_revision_id:
        raise SourcingConflictError("The RFQ was amended; submit against the current revision")


async def acknowledge_invitation(
    context: RequestContext,
    invitation_id: uuid.UUID,
    payload: InvitationAcknowledge,
) -> InvitationRead:
    invitation, rfq = await _locked_invitation_and_rfq(
        context, invitation_id, payload.expected_rfq_version
    )
    now = _require_open_invitation_response(rfq)
    if invitation.status is not InvitationStatus.INVITED:
        raise SourcingConflictError(
            f"Only an invited supplier can acknowledge; invitation is {invitation.status.value}"
        )
    invitation.status = InvitationStatus.ACKNOWLEDGED
    invitation.responded_at = now
    invitation.response_reason = None
    rfq.version += 1
    _record_change(
        context,
        rfq,
        "rfq.invitation_acknowledged",
        {
            "invitation_id": str(invitation.id),
            "supplier_id": str(invitation.supplier_id),
        },
    )
    await context.session.flush()
    return InvitationRead.model_validate(invitation)


async def decline_invitation(
    context: RequestContext,
    invitation_id: uuid.UUID,
    payload: InvitationNoBid,
) -> InvitationRead:
    invitation, rfq = await _locked_invitation_and_rfq(
        context, invitation_id, payload.expected_rfq_version
    )
    now = _require_open_invitation_response(rfq)
    if invitation.status not in {InvitationStatus.INVITED, InvitationStatus.ACKNOWLEDGED}:
        raise SourcingConflictError(
            f"Invitation in {invitation.status.value} state cannot be declined"
        )
    invitation.status = InvitationStatus.NO_BID
    invitation.responded_at = now
    invitation.response_reason = payload.reason
    rfq.version += 1
    _record_change(
        context,
        rfq,
        "rfq.invitation_declined",
        {
            "invitation_id": str(invitation.id),
            "supplier_id": str(invitation.supplier_id),
            "reason": payload.reason,
        },
    )
    await context.session.flush()
    return InvitationRead.model_validate(invitation)


async def _publication_snapshot(context: RequestContext, rfq: Rfq) -> RfqRevision:
    view = await read_rfq(context, rfq.id)
    snapshot = view.model_dump(
        mode="json",
        exclude={
            "invitations",
            "submissions",
            "clarifications",
            "created_at",
            "updated_at",
        },
    )
    digest = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    revision = RfqRevision(
        id=uuid.uuid4(),
        organization_id=context.organization_id,
        rfq_id=rfq.id,
        publication_number=rfq.publication_number,
        snapshot=snapshot,
        content_digest=digest,
        created_by_user_id=context.user_id,
    )
    context.session.add(revision)
    await context.session.flush()
    return revision


async def publish_rfq(
    context: RequestContext, rfq_id: uuid.UUID, payload: RfqTransition
) -> RfqRead:
    rfq = await _locked_rfq(context, rfq_id)
    _check_version(rfq, payload.expected_version)
    if rfq.status is not RfqStatus.DRAFT:
        raise SourcingConflictError("Only a draft RFQ can be published")
    _require_future_deadline(rfq.submission_deadline)
    invitation_count = await context.session.scalar(
        select(func.count(RfqInvitation.id)).where(
            RfqInvitation.organization_id == context.organization_id,
            RfqInvitation.rfq_id == rfq.id,
        )
    )
    if not invitation_count:
        raise SourcingValidationError("At least one approved supplier must be invited")
    now = datetime.now(UTC)
    rfq.version += 1
    rfq.publication_number = 1
    rfq.status = RfqStatus.PUBLISHED
    rfq.published_at = now
    await context.session.flush()
    revision = await _publication_snapshot(context, rfq)
    invitations = await context.session.scalars(
        select(RfqInvitation).where(
            RfqInvitation.organization_id == context.organization_id,
            RfqInvitation.rfq_id == rfq.id,
        )
    )
    for invitation in invitations:
        invitation.rfq_revision_id = revision.id
        invitation.invited_at = now
    requisition = await context.session.scalar(
        select(Requisition)
        .where(
            Requisition.organization_id == context.organization_id,
            Requisition.id == rfq.requisition_id,
        )
        .with_for_update()
    )
    if requisition is None or requisition.status is not RequisitionStatus.APPROVED:
        raise SourcingConflictError("The source requisition is no longer approved")
    requisition.status = RequisitionStatus.SOURCING
    requisition.version += 1
    _record_change(
        context,
        rfq,
        "rfq.published",
        {"publication_number": rfq.publication_number, "digest": revision.content_digest},
    )
    await context.session.flush()
    return await read_rfq(context, rfq.id)


async def amend_rfq(context: RequestContext, rfq_id: uuid.UUID, payload: RfqAmend) -> RfqRead:
    _require_future_deadline(payload.submission_deadline)
    rfq = await _locked_rfq(context, rfq_id)
    _check_version(rfq, payload.expected_version)
    if rfq.status is not RfqStatus.PUBLISHED:
        raise SourcingConflictError("Only a published RFQ can be amended")
    rfq.submission_deadline = payload.submission_deadline
    rfq.terms = payload.terms
    rfq.version += 1
    rfq.publication_number += 1
    await context.session.flush()
    revision = await _publication_snapshot(context, rfq)
    invitations = await context.session.scalars(
        select(RfqInvitation).where(
            RfqInvitation.organization_id == context.organization_id,
            RfqInvitation.rfq_id == rfq.id,
            RfqInvitation.status != InvitationStatus.REVOKED,
        )
    )
    for invitation in invitations:
        invitation.rfq_revision_id = revision.id
    _record_change(
        context,
        rfq,
        "rfq.amended",
        {
            "publication_number": rfq.publication_number,
            "digest": revision.content_digest,
            "reason": payload.reason,
        },
    )
    await context.session.flush()
    return await read_rfq(context, rfq.id)


async def submit_quote(
    context: RequestContext, invitation_id: uuid.UUID, payload: SubmissionCreate
) -> SubmissionRead:
    invitation = await context.session.scalar(
        select(RfqInvitation).where(
            RfqInvitation.organization_id == context.organization_id,
            RfqInvitation.id == invitation_id,
        )
    )
    if invitation is None:
        raise SourcingNotFoundError("Invitation not found")
    rfq = await _locked_rfq(context, invitation.rfq_id)
    invitation = await context.session.scalar(
        select(RfqInvitation)
        .where(
            RfqInvitation.organization_id == context.organization_id,
            RfqInvitation.rfq_id == rfq.id,
            RfqInvitation.id == invitation_id,
        )
        .with_for_update()
    )
    if invitation is None:
        raise SourcingNotFoundError("Invitation not found")
    if rfq.status is not RfqStatus.PUBLISHED:
        raise SourcingConflictError("The RFQ is not accepting submissions")
    now = datetime.now(UTC)
    if now > rfq.submission_deadline.astimezone(UTC):
        raise SourcingValidationError("The submission deadline has passed")
    if invitation.status in {InvitationStatus.NO_BID, InvitationStatus.REVOKED}:
        raise SourcingConflictError(f"Invitation is {invitation.status.value}")
    _require_current_revision(invitation, payload.rfq_revision_id)
    supplier_status = await context.session.scalar(
        select(Supplier.status).where(
            Supplier.organization_id == context.organization_id,
            Supplier.id == invitation.supplier_id,
        )
    )
    if supplier_status is not SupplierStatus.APPROVED:
        raise SourcingValidationError("Supplier is no longer approved")
    if payload.currency != rfq.currency:
        raise SourcingValidationError("Quote currency must match the RFQ currency")
    if payload.valid_until < rfq.submission_deadline.date():
        raise SourcingValidationError("Quote validity must extend through the RFQ deadline")

    items = {
        item.id: item
        for item in await context.session.scalars(
            select(RfqItem).where(
                RfqItem.organization_id == context.organization_id,
                RfqItem.rfq_id == rfq.id,
                RfqItem.id.in_([line.rfq_item_id for line in payload.lines]),
            )
        )
    }
    if len(items) != len(payload.lines):
        raise SourcingValidationError("One or more quote lines reference an unknown RFQ item")
    for line in payload.lines:
        if line.is_alternative and not items[line.rfq_item_id].alternatives_allowed:
            raise SourcingValidationError("An alternative was offered for a restricted RFQ item")

    current_version = await context.session.scalar(
        select(func.max(QuoteSubmission.version)).where(
            QuoteSubmission.organization_id == context.organization_id,
            QuoteSubmission.invitation_id == invitation.id,
        )
    )
    version = (current_version or 0) + 1
    previous = await context.session.scalar(
        select(QuoteSubmission)
        .where(
            QuoteSubmission.organization_id == context.organization_id,
            QuoteSubmission.invitation_id == invitation.id,
            QuoteSubmission.status == SubmissionStatus.SUBMITTED,
        )
        .with_for_update()
    )
    if previous is not None:
        previous.status = SubmissionStatus.SUPERSEDED
    snapshot = payload.model_dump(mode="json")
    digest = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    submission = QuoteSubmission(
        id=uuid.uuid4(),
        organization_id=context.organization_id,
        rfq_id=rfq.id,
        invitation_id=invitation.id,
        supplier_id=invitation.supplier_id,
        rfq_revision_id=payload.rfq_revision_id,
        version=version,
        currency=payload.currency,
        valid_until=payload.valid_until,
        delivery_terms=payload.delivery_terms,
        payment_terms=payload.payment_terms,
        notes=payload.notes,
        status=SubmissionStatus.SUBMITTED,
        snapshot=snapshot,
        content_digest=digest,
        submitted_by_user_id=context.user_id,
        submitted_at=now,
    )
    context.session.add(submission)
    context.session.add_all(
        [
            QuoteLine(
                organization_id=context.organization_id,
                rfq_id=rfq.id,
                submission_id=submission.id,
                rfq_item_id=line.rfq_item_id,
                quantity=line.quantity,
                unit_price=line.unit_price,
                tax_amount=line.tax_amount,
                freight_amount=line.freight_amount,
                is_alternative=line.is_alternative,
                description=line.description,
            )
            for line in payload.lines
        ]
    )
    invitation.status = InvitationStatus.SUBMITTED
    invitation.responded_at = now
    rfq.version += 1
    _record_change(
        context,
        rfq,
        "quote.submitted",
        {
            "submission_id": str(submission.id),
            "supplier_id": str(invitation.supplier_id),
            "submission_version": version,
            "digest": digest,
        },
    )
    await context.session.flush()
    return await read_submission(context, submission.id)


async def withdraw_quote(
    context: RequestContext, submission_id: uuid.UUID, payload: SubmissionWithdraw
) -> SubmissionRead:
    candidate = await context.session.scalar(
        select(QuoteSubmission).where(
            QuoteSubmission.organization_id == context.organization_id,
            QuoteSubmission.id == submission_id,
        )
    )
    if candidate is None:
        raise SourcingNotFoundError("Submission not found")
    rfq = await _locked_rfq(context, candidate.rfq_id)
    _check_version(rfq, payload.expected_rfq_version)
    submission = await context.session.scalar(
        select(QuoteSubmission)
        .where(
            QuoteSubmission.organization_id == context.organization_id,
            QuoteSubmission.rfq_id == rfq.id,
            QuoteSubmission.id == submission_id,
        )
        .with_for_update()
    )
    if submission is None:
        raise SourcingNotFoundError("Submission not found")
    if rfq.status is not RfqStatus.PUBLISHED:
        raise SourcingConflictError("The RFQ is not accepting withdrawal")
    if datetime.now(UTC) > rfq.submission_deadline.astimezone(UTC):
        raise SourcingValidationError("A quote cannot be withdrawn after the deadline")
    if submission.status is not SubmissionStatus.SUBMITTED:
        raise SourcingConflictError("Only the current submitted quote can be withdrawn")
    latest_version = await context.session.scalar(
        select(func.max(QuoteSubmission.version)).where(
            QuoteSubmission.organization_id == context.organization_id,
            QuoteSubmission.invitation_id == submission.invitation_id,
        )
    )
    if submission.version != latest_version:
        raise SourcingConflictError("Only the latest quote version can be withdrawn")
    invitation = await context.session.scalar(
        select(RfqInvitation)
        .where(
            RfqInvitation.organization_id == context.organization_id,
            RfqInvitation.rfq_id == rfq.id,
            RfqInvitation.id == submission.invitation_id,
        )
        .with_for_update()
    )
    if invitation is None:
        raise SourcingNotFoundError("Invitation not found")
    submission.status = SubmissionStatus.WITHDRAWN
    submission.withdrawn_at = datetime.now(UTC)
    invitation.status = InvitationStatus.ACKNOWLEDGED
    invitation.responded_at = submission.withdrawn_at
    rfq.version += 1
    _record_change(
        context,
        rfq,
        "quote.withdrawn",
        {
            "submission_id": str(submission.id),
            "supplier_id": str(submission.supplier_id),
            "reason": payload.reason,
        },
    )
    await context.session.flush()
    return await read_submission(context, submission.id)


async def create_clarification(
    context: RequestContext, rfq_id: uuid.UUID, payload: ClarificationCreate
) -> ClarificationRead:
    rfq = await _locked_rfq(context, rfq_id)
    if rfq.status is not RfqStatus.PUBLISHED:
        raise SourcingConflictError("Clarifications require a published RFQ")
    if datetime.now(UTC) > rfq.submission_deadline.astimezone(UTC):
        raise SourcingValidationError("The clarification window is closed")
    if payload.invitation_id is not None:
        invitation = await context.session.scalar(
            select(RfqInvitation.id).where(
                RfqInvitation.organization_id == context.organization_id,
                RfqInvitation.rfq_id == rfq.id,
                RfqInvitation.id == payload.invitation_id,
            )
        )
        if invitation is None:
            raise SourcingNotFoundError("Invitation not found")
    clarification = RfqClarification(
        id=uuid.uuid4(),
        organization_id=context.organization_id,
        rfq_id=rfq.id,
        invitation_id=payload.invitation_id,
        visibility=payload.visibility,
        status=ClarificationStatus.OPEN,
        question=payload.question,
        asked_by_user_id=context.user_id,
    )
    context.session.add(clarification)
    rfq.version += 1
    _record_change(
        context,
        rfq,
        "rfq.clarification.created",
        {"clarification_id": str(clarification.id), "visibility": payload.visibility.value},
    )
    await context.session.flush()
    return ClarificationRead.model_validate(clarification)


async def answer_clarification(
    context: RequestContext,
    rfq_id: uuid.UUID,
    clarification_id: uuid.UUID,
    payload: ClarificationAnswer,
) -> ClarificationRead:
    rfq = await _locked_rfq(context, rfq_id)
    if rfq.status is not RfqStatus.PUBLISHED:
        raise SourcingConflictError("The RFQ is not open for clarifications")
    clarification = await context.session.scalar(
        select(RfqClarification)
        .where(
            RfqClarification.organization_id == context.organization_id,
            RfqClarification.rfq_id == rfq.id,
            RfqClarification.id == clarification_id,
        )
        .with_for_update()
    )
    if clarification is None:
        raise SourcingNotFoundError("Clarification not found")
    if clarification.status is not ClarificationStatus.OPEN:
        raise SourcingConflictError("Clarification has already been answered")
    clarification.answer = payload.answer
    clarification.status = ClarificationStatus.ANSWERED
    clarification.answered_by_user_id = context.user_id
    clarification.answered_at = datetime.now(UTC)
    rfq.version += 1
    _record_change(
        context,
        rfq,
        "rfq.clarification.answered",
        {
            "clarification_id": str(clarification.id),
            "visibility": clarification.visibility.value,
        },
    )
    await context.session.flush()
    return ClarificationRead.model_validate(clarification)


async def cancel_rfq(context: RequestContext, rfq_id: uuid.UUID, payload: RfqCancel) -> RfqRead:
    rfq = await _locked_rfq(context, rfq_id)
    _check_version(rfq, payload.expected_version)
    if rfq.status not in {RfqStatus.DRAFT, RfqStatus.PUBLISHED}:
        raise SourcingConflictError(f"Cannot cancel an RFQ in {rfq.status.value} state")
    was_published = rfq.status is RfqStatus.PUBLISHED
    rfq.status = RfqStatus.CANCELLED
    rfq.cancelled_at = datetime.now(UTC)
    rfq.cancellation_reason = payload.reason
    rfq.version += 1
    if was_published:
        requisition = await context.session.scalar(
            select(Requisition)
            .where(
                Requisition.organization_id == context.organization_id,
                Requisition.id == rfq.requisition_id,
            )
            .with_for_update()
        )
        if requisition is None:
            raise SourcingNotFoundError("Source requisition not found")
        if requisition.status is RequisitionStatus.SOURCING:
            requisition.status = RequisitionStatus.APPROVED
            requisition.version += 1
    _record_change(context, rfq, "rfq.cancelled", {"reason": payload.reason})
    await context.session.flush()
    return await read_rfq(context, rfq.id)


async def close_rfq(context: RequestContext, rfq_id: uuid.UUID, payload: RfqTransition) -> RfqRead:
    rfq = await _locked_rfq(context, rfq_id)
    _check_version(rfq, payload.expected_version)
    if rfq.status is not RfqStatus.PUBLISHED:
        raise SourcingConflictError("Only a published RFQ can be closed")
    if datetime.now(UTC) < rfq.submission_deadline.astimezone(UTC):
        raise SourcingValidationError("RFQ cannot close before its submission deadline")
    rfq.status = RfqStatus.CLOSED
    rfq.closed_at = datetime.now(UTC)
    rfq.version += 1
    _record_change(context, rfq, "rfq.closed", {})
    await context.session.flush()
    return await read_rfq(context, rfq.id)


async def read_submission(context: RequestContext, submission_id: uuid.UUID) -> SubmissionRead:
    submission = await context.session.scalar(
        select(QuoteSubmission).where(
            QuoteSubmission.organization_id == context.organization_id,
            QuoteSubmission.id == submission_id,
        )
    )
    if submission is None:
        raise SourcingNotFoundError("Submission not found")
    lines = list(
        await context.session.scalars(
            select(QuoteLine)
            .where(
                QuoteLine.organization_id == context.organization_id,
                QuoteLine.submission_id == submission.id,
            )
            .order_by(QuoteLine.rfq_item_id)
        )
    )
    return SubmissionRead(
        id=submission.id,
        invitation_id=submission.invitation_id,
        supplier_id=submission.supplier_id,
        rfq_revision_id=submission.rfq_revision_id,
        version=submission.version,
        currency=submission.currency,
        valid_until=submission.valid_until,
        delivery_terms=submission.delivery_terms,
        payment_terms=submission.payment_terms,
        notes=submission.notes,
        status=submission.status,
        content_digest=submission.content_digest,
        submitted_at=submission.submitted_at,
        withdrawn_at=submission.withdrawn_at,
        lines=[SubmissionLineRead.model_validate(line) for line in lines],
    )


async def read_rfq(context: RequestContext, rfq_id: uuid.UUID) -> RfqRead:
    rfq = await context.session.scalar(
        select(Rfq).where(Rfq.organization_id == context.organization_id, Rfq.id == rfq_id)
    )
    if rfq is None:
        raise SourcingNotFoundError("RFQ not found")
    items = list(
        await context.session.scalars(
            select(RfqItem)
            .where(RfqItem.organization_id == context.organization_id, RfqItem.rfq_id == rfq.id)
            .order_by(RfqItem.line_number)
        )
    )
    requirements = list(
        await context.session.scalars(
            select(RfqRequirement)
            .where(
                RfqRequirement.organization_id == context.organization_id,
                RfqRequirement.rfq_id == rfq.id,
            )
            .order_by(RfqRequirement.created_at, RfqRequirement.id)
        )
    )
    invitations = list(
        await context.session.scalars(
            select(RfqInvitation)
            .where(
                RfqInvitation.organization_id == context.organization_id,
                RfqInvitation.rfq_id == rfq.id,
            )
            .order_by(RfqInvitation.created_at, RfqInvitation.id)
        )
    )
    submissions = list(
        await context.session.scalars(
            select(QuoteSubmission.id)
            .where(
                QuoteSubmission.organization_id == context.organization_id,
                QuoteSubmission.rfq_id == rfq.id,
            )
            .order_by(QuoteSubmission.supplier_id, QuoteSubmission.version)
        )
    )
    clarifications = list(
        await context.session.scalars(
            select(RfqClarification)
            .where(
                RfqClarification.organization_id == context.organization_id,
                RfqClarification.rfq_id == rfq.id,
            )
            .order_by(RfqClarification.created_at, RfqClarification.id)
        )
    )
    return RfqRead(
        id=rfq.id,
        organization_id=rfq.organization_id,
        requisition_id=rfq.requisition_id,
        title=rfq.title,
        currency=rfq.currency,
        submission_deadline=rfq.submission_deadline,
        terms=rfq.terms,
        status=rfq.status,
        version=rfq.version,
        publication_number=rfq.publication_number,
        published_at=rfq.published_at,
        closed_at=rfq.closed_at,
        cancelled_at=rfq.cancelled_at,
        cancellation_reason=rfq.cancellation_reason,
        created_at=rfq.created_at,
        updated_at=rfq.updated_at,
        items=[RfqItemRead.model_validate(item) for item in items],
        requirements=[RfqRequirementRead.model_validate(item) for item in requirements],
        invitations=[InvitationRead.model_validate(item) for item in invitations],
        submissions=[await read_submission(context, item) for item in submissions],
        clarifications=[ClarificationRead.model_validate(item) for item in clarifications],
    )


async def list_rfqs(context: RequestContext, limit: int, offset: int) -> RfqList:
    ids = list(
        await context.session.scalars(
            select(Rfq.id)
            .where(Rfq.organization_id == context.organization_id)
            .order_by(Rfq.created_at.desc(), Rfq.id)
            .limit(limit)
            .offset(offset)
        )
    )
    total = await context.session.scalar(
        select(func.count(Rfq.id)).where(Rfq.organization_id == context.organization_id)
    )
    return RfqList(items=[await read_rfq(context, rfq_id) for rfq_id in ids], total=total or 0)
