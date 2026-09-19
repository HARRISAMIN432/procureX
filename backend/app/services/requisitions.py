import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select

from app.auth.context import RequestContext
from app.models.approvals import ApprovalRequest, ApprovalRequestStatus
from app.models.platform import ActorType, AuditEvent, OutboxEvent
from app.models.requisitions import (
    Requisition,
    RequisitionLine,
    RequisitionRequirement,
    RequisitionRevision,
    RequisitionStatus,
)
from app.schemas.requisitions import (
    RequisitionCancel,
    RequisitionCreate,
    RequisitionLineRead,
    RequisitionList,
    RequisitionRead,
    RequisitionReplace,
    RequisitionRequirementRead,
    RequisitionTransition,
)


class RequisitionNotFoundError(ValueError):
    pass


class RequisitionVersionConflictError(ValueError):
    pass


class RequisitionStateError(ValueError):
    pass


class RequisitionValidationError(ValueError):
    pass


async def _locked_requisition(context: RequestContext, requisition_id: uuid.UUID) -> Requisition:
    requisition = await context.session.scalar(
        select(Requisition)
        .where(
            Requisition.organization_id == context.organization_id,
            Requisition.id == requisition_id,
        )
        .with_for_update()
    )
    if requisition is None:
        raise RequisitionNotFoundError(str(requisition_id))
    return requisition


def _check_version(requisition: Requisition, expected_version: int) -> None:
    if requisition.version != expected_version:
        raise RequisitionVersionConflictError(
            f"Expected version {expected_version}, current version is {requisition.version}"
        )


def _record_change(
    context: RequestContext,
    requisition: Requisition,
    action: str,
    changes: dict[str, object],
) -> None:
    context.session.add_all(
        [
            AuditEvent(
                organization_id=context.organization_id,
                actor_type=ActorType.USER,
                actor_id=context.user_id,
                action=action,
                object_type="requisition",
                object_id=requisition.id,
                object_version=requisition.version,
                changes=changes,
            ),
            OutboxEvent(
                organization_id=context.organization_id,
                aggregate_type="requisition",
                aggregate_id=requisition.id,
                aggregate_version=requisition.version,
                event_type=action,
                schema_version=1,
                payload={
                    "requisition_id": str(requisition.id),
                    "version": requisition.version,
                    "status": requisition.status.value,
                },
                actor_id=context.user_id,
            ),
        ]
    )


def _apply_header(
    requisition: Requisition, payload: RequisitionCreate | RequisitionReplace
) -> None:
    requisition.title = payload.title
    requisition.justification = payload.justification
    requisition.department = payload.department
    requisition.cost_center = payload.cost_center
    requisition.currency = payload.currency
    requisition.need_by_date = payload.need_by_date
    requisition.delivery_location = payload.delivery_location


async def _replace_children(
    context: RequestContext,
    requisition: Requisition,
    payload: RequisitionCreate | RequisitionReplace,
) -> None:
    await context.session.execute(
        delete(RequisitionRequirement).where(
            RequisitionRequirement.organization_id == context.organization_id,
            RequisitionRequirement.requisition_id == requisition.id,
        )
    )
    await context.session.execute(
        delete(RequisitionLine).where(
            RequisitionLine.organization_id == context.organization_id,
            RequisitionLine.requisition_id == requisition.id,
        )
    )

    line_ids = {line.line_number: uuid.uuid4() for line in payload.lines}
    context.session.add_all(
        [
            RequisitionLine(
                id=line_ids[line.line_number],
                organization_id=context.organization_id,
                requisition_id=requisition.id,
                line_number=line.line_number,
                description=line.description,
                quantity=line.quantity,
                unit=line.unit,
                estimated_unit_price=line.estimated_unit_price,
                category=line.category,
                specifications=line.specifications,
                alternatives_allowed=line.alternatives_allowed,
            )
            for line in payload.lines
        ]
    )
    context.session.add_all(
        [
            RequisitionRequirement(
                organization_id=context.organization_id,
                requisition_id=requisition.id,
                line_id=(
                    line_ids[requirement.line_number]
                    if requirement.line_number is not None
                    else None
                ),
                priority=requirement.priority,
                criterion=requirement.criterion,
                verification_method=requirement.verification_method,
                source=requirement.source,
                confirmed_by_user_id=context.user_id if requirement.confirmed else None,
            )
            for requirement in payload.requirements
        ]
    )


async def create_requisition(
    context: RequestContext, payload: RequisitionCreate
) -> RequisitionRead:
    requisition = Requisition(
        id=uuid.uuid4(),
        organization_id=context.organization_id,
        title=payload.title,
        justification=payload.justification,
        department=payload.department,
        cost_center=payload.cost_center,
        currency=payload.currency,
        need_by_date=payload.need_by_date,
        delivery_location=payload.delivery_location,
        status=RequisitionStatus.DRAFT,
        version=1,
        created_by_user_id=context.user_id,
    )
    context.session.add(requisition)
    await context.session.flush()
    await _replace_children(context, requisition, payload)
    _record_change(
        context,
        requisition,
        "requisition.created",
        {"line_count": len(payload.lines), "requirement_count": len(payload.requirements)},
    )
    await context.session.flush()
    return await read_requisition(context, requisition.id)


async def replace_requisition(
    context: RequestContext,
    requisition_id: uuid.UUID,
    payload: RequisitionReplace,
) -> RequisitionRead:
    requisition = await _locked_requisition(context, requisition_id)
    _check_version(requisition, payload.expected_version)
    if requisition.status not in {
        RequisitionStatus.DRAFT,
        RequisitionStatus.CHANGES_REQUESTED,
    }:
        raise RequisitionStateError(f"Cannot edit requisition in {requisition.status.value} state")

    _apply_header(requisition, payload)
    await _replace_children(context, requisition, payload)
    requisition.version += 1
    _record_change(
        context,
        requisition,
        "requisition.updated",
        {"line_count": len(payload.lines), "requirement_count": len(payload.requirements)},
    )
    await context.session.flush()
    return await read_requisition(context, requisition.id)


async def submit_requisition(
    context: RequestContext,
    requisition_id: uuid.UUID,
    payload: RequisitionTransition,
) -> RequisitionRead:
    requisition = await _locked_requisition(context, requisition_id)
    _check_version(requisition, payload.expected_version)
    if requisition.status not in {
        RequisitionStatus.DRAFT,
        RequisitionStatus.CHANGES_REQUESTED,
    }:
        raise RequisitionStateError(
            f"Cannot submit requisition in {requisition.status.value} state"
        )

    line_count = await context.session.scalar(
        select(func.count(RequisitionLine.id)).where(
            RequisitionLine.organization_id == context.organization_id,
            RequisitionLine.requisition_id == requisition.id,
        )
    )
    if not line_count:
        raise RequisitionValidationError("At least one line item is required before submission")
    unconfirmed_count = await context.session.scalar(
        select(func.count(RequisitionRequirement.id)).where(
            RequisitionRequirement.organization_id == context.organization_id,
            RequisitionRequirement.requisition_id == requisition.id,
            RequisitionRequirement.confirmed_by_user_id.is_(None),
        )
    )
    if unconfirmed_count:
        raise RequisitionValidationError(
            "All AI-assisted or draft requirements must be confirmed before submission"
        )

    requisition.version += 1
    requisition.status = RequisitionStatus.SUBMITTED
    requisition.submitted_at = datetime.now(UTC)
    await context.session.flush()
    view = await read_requisition(context, requisition.id)
    snapshot = view.model_dump(mode="json")
    content_digest = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    context.session.add(
        RequisitionRevision(
            organization_id=context.organization_id,
            requisition_id=requisition.id,
            version=requisition.version,
            snapshot=snapshot,
            content_digest=content_digest,
            created_by_user_id=context.user_id,
        )
    )
    _record_change(
        context,
        requisition,
        "requisition.submitted",
        {"content_digest": content_digest},
    )
    return view


async def cancel_requisition(
    context: RequestContext,
    requisition_id: uuid.UUID,
    payload: RequisitionCancel,
) -> RequisitionRead:
    requisition = await _locked_requisition(context, requisition_id)
    _check_version(requisition, payload.expected_version)
    if requisition.status not in {
        RequisitionStatus.DRAFT,
        RequisitionStatus.SUBMITTED,
        RequisitionStatus.CHANGES_REQUESTED,
    }:
        raise RequisitionStateError(
            f"Cannot cancel requisition in {requisition.status.value} state"
        )
    requisition.version += 1
    requisition.status = RequisitionStatus.CANCELLED
    requisition.cancelled_at = datetime.now(UTC)
    requisition.cancellation_reason = payload.reason.strip()
    pending_approval = await context.session.scalar(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.organization_id == context.organization_id,
            ApprovalRequest.requisition_id == requisition.id,
            ApprovalRequest.status == ApprovalRequestStatus.PENDING,
        )
        .with_for_update()
    )
    if pending_approval is not None:
        pending_approval.status = ApprovalRequestStatus.CANCELLED
        pending_approval.completed_at = requisition.cancelled_at
        context.session.add_all(
            [
                AuditEvent(
                    organization_id=context.organization_id,
                    actor_type=ActorType.USER,
                    actor_id=context.user_id,
                    action="approval.cancelled",
                    object_type="approval_request",
                    object_id=pending_approval.id,
                    object_version=1,
                    changes={"requisition_id": str(requisition.id)},
                ),
                OutboxEvent(
                    organization_id=context.organization_id,
                    aggregate_type="approval_request",
                    aggregate_id=pending_approval.id,
                    aggregate_version=1,
                    event_type="approval.cancelled",
                    schema_version=1,
                    payload={"requisition_id": str(requisition.id)},
                    actor_id=context.user_id,
                ),
            ]
        )
    _record_change(
        context,
        requisition,
        "requisition.cancelled",
        {"reason": requisition.cancellation_reason},
    )
    await context.session.flush()
    return await read_requisition(context, requisition.id)


async def read_requisition(context: RequestContext, requisition_id: uuid.UUID) -> RequisitionRead:
    requisition = await context.session.scalar(
        select(Requisition).where(
            Requisition.organization_id == context.organization_id,
            Requisition.id == requisition_id,
        )
    )
    if requisition is None:
        raise RequisitionNotFoundError(str(requisition_id))
    lines = list(
        await context.session.scalars(
            select(RequisitionLine)
            .where(
                RequisitionLine.organization_id == context.organization_id,
                RequisitionLine.requisition_id == requisition.id,
            )
            .order_by(RequisitionLine.line_number)
        )
    )
    requirements = list(
        await context.session.scalars(
            select(RequisitionRequirement)
            .where(
                RequisitionRequirement.organization_id == context.organization_id,
                RequisitionRequirement.requisition_id == requisition.id,
            )
            .order_by(RequisitionRequirement.created_at, RequisitionRequirement.id)
        )
    )
    line_numbers = {line.id: line.line_number for line in lines}
    return RequisitionRead(
        id=requisition.id,
        organization_id=requisition.organization_id,
        title=requisition.title,
        justification=requisition.justification,
        department=requisition.department,
        cost_center=requisition.cost_center,
        currency=requisition.currency,
        need_by_date=requisition.need_by_date,
        delivery_location=requisition.delivery_location,
        status=requisition.status,
        version=requisition.version,
        created_by_user_id=requisition.created_by_user_id,
        submitted_at=requisition.submitted_at,
        cancelled_at=requisition.cancelled_at,
        cancellation_reason=requisition.cancellation_reason,
        created_at=requisition.created_at,
        updated_at=requisition.updated_at,
        lines=[RequisitionLineRead.model_validate(line) for line in lines],
        requirements=[
            RequisitionRequirementRead(
                id=requirement.id,
                line_id=requirement.line_id,
                line_number=(
                    line_numbers.get(requirement.line_id)
                    if requirement.line_id is not None
                    else None
                ),
                priority=requirement.priority,
                criterion=requirement.criterion,
                verification_method=requirement.verification_method,
                source=requirement.source,
                confirmed_by_user_id=requirement.confirmed_by_user_id,
            )
            for requirement in requirements
        ],
    )


async def list_requisitions(
    context: RequestContext,
    limit: int,
    offset: int,
) -> RequisitionList:
    ids = list(
        await context.session.scalars(
            select(Requisition.id)
            .where(Requisition.organization_id == context.organization_id)
            .order_by(Requisition.created_at.desc(), Requisition.id)
            .limit(limit)
            .offset(offset)
        )
    )
    total = await context.session.scalar(
        select(func.count(Requisition.id)).where(
            Requisition.organization_id == context.organization_id
        )
    )
    return RequisitionList(
        items=[await read_requisition(context, requisition_id) for requisition_id in ids],
        total=total or 0,
    )
