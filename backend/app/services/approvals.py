import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Decimal

from sqlalchemy import func, select

from app.auth.context import RequestContext
from app.models.approvals import (
    ApprovalDecision,
    ApprovalDecisionValue,
    ApprovalPolicy,
    ApprovalPolicyStatus,
    ApprovalRequest,
    ApprovalRequestStatus,
    Budget,
    BudgetEntryType,
    BudgetLedgerEntry,
    BudgetReservation,
    BudgetStatus,
)
from app.models.identity import Organization
from app.models.platform import ActorType, AuditEvent, OutboxEvent
from app.models.requisitions import (
    Requisition,
    RequisitionLine,
    RequisitionRevision,
    RequisitionStatus,
)
from app.schemas.approvals import (
    ApprovalDecisionRead,
    ApprovalDecisionWrite,
    ApprovalPolicyCreate,
    ApprovalPolicyRead,
    ApprovalRequestCreate,
    ApprovalRequestRead,
    BudgetCreate,
    BudgetList,
    BudgetRead,
)

ZERO = Decimal("0")
MONEY_QUANTUM = Decimal("0.0001")


class ControlNotFoundError(ValueError):
    pass


class ControlConflictError(ValueError):
    pass


class ControlValidationError(ValueError):
    pass


async def _budget_balances(context: RequestContext, budget_id: uuid.UUID) -> tuple[Decimal, ...]:
    row = (
        await context.session.execute(
            select(
                func.coalesce(func.sum(BudgetLedgerEntry.delta_available), 0),
                func.coalesce(func.sum(BudgetLedgerEntry.delta_reserved), 0),
                func.coalesce(func.sum(BudgetLedgerEntry.delta_committed), 0),
                func.coalesce(func.sum(BudgetLedgerEntry.delta_consumed), 0),
            ).where(
                BudgetLedgerEntry.organization_id == context.organization_id,
                BudgetLedgerEntry.budget_id == budget_id,
            )
        )
    ).one()
    return tuple(Decimal(value) for value in row)


async def _budget_read(context: RequestContext, budget: Budget) -> BudgetRead:
    available, reserved, committed, consumed = await _budget_balances(context, budget.id)
    return BudgetRead(
        id=budget.id,
        organization_id=budget.organization_id,
        code=budget.code,
        name=budget.name,
        currency=budget.currency,
        period_start=budget.period_start,
        period_end=budget.period_end,
        status=budget.status,
        version=budget.version,
        available=available,
        reserved=reserved,
        committed=committed,
        consumed=consumed,
        created_at=budget.created_at,
        updated_at=budget.updated_at,
    )


def _audit_and_event(
    context: RequestContext,
    *,
    action: str,
    object_type: str,
    object_id: uuid.UUID,
    object_version: int,
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
                object_version=object_version,
                changes=changes,
            ),
            OutboxEvent(
                organization_id=context.organization_id,
                aggregate_type=object_type,
                aggregate_id=object_id,
                aggregate_version=object_version,
                event_type=action,
                schema_version=1,
                payload={"id": str(object_id), **changes},
                actor_id=context.user_id,
            ),
        ]
    )


async def create_budget(context: RequestContext, payload: BudgetCreate) -> BudgetRead:
    await context.session.execute(
        select(Organization.id).where(Organization.id == context.organization_id).with_for_update()
    )
    existing = await context.session.scalar(
        select(Budget.id).where(
            Budget.organization_id == context.organization_id,
            Budget.code == payload.code,
        )
    )
    if existing is not None:
        raise ControlConflictError(f"Budget code '{payload.code}' already exists")
    budget = Budget(
        id=uuid.uuid4(),
        organization_id=context.organization_id,
        code=payload.code,
        name=payload.name.strip(),
        currency=payload.currency,
        period_start=payload.period_start,
        period_end=payload.period_end,
        status=BudgetStatus.ACTIVE,
        version=1,
        created_by_user_id=context.user_id,
    )
    context.session.add(budget)
    await context.session.flush()
    if payload.initial_allocation > ZERO:
        context.session.add(
            BudgetLedgerEntry(
                organization_id=context.organization_id,
                budget_id=budget.id,
                requisition_id=None,
                entry_type=BudgetEntryType.ALLOCATION,
                delta_available=payload.initial_allocation,
                delta_reserved=ZERO,
                delta_committed=ZERO,
                delta_consumed=ZERO,
                idempotency_key=f"budget:{budget.id}:initial-allocation",
                reference_type="budget",
                reference_id=budget.id,
                reason="Initial budget allocation",
                actor_user_id=context.user_id,
                occurred_at=datetime.now(UTC),
            )
        )
    _audit_and_event(
        context,
        action="budget.created",
        object_type="budget",
        object_id=budget.id,
        object_version=budget.version,
        changes={"code": budget.code, "initial_allocation": str(payload.initial_allocation)},
    )
    await context.session.flush()
    return await _budget_read(context, budget)


async def list_budgets(context: RequestContext) -> BudgetList:
    budgets = list(
        await context.session.scalars(
            select(Budget)
            .where(Budget.organization_id == context.organization_id)
            .order_by(Budget.code)
        )
    )
    return BudgetList(
        items=[await _budget_read(context, budget) for budget in budgets],
        total=len(budgets),
    )


async def create_approval_policy(
    context: RequestContext, payload: ApprovalPolicyCreate
) -> ApprovalPolicyRead:
    effective_from = payload.effective_from or datetime.now(UTC)
    await context.session.execute(
        select(Organization.id).where(Organization.id == context.organization_id).with_for_update()
    )
    current = await context.session.scalar(
        select(ApprovalPolicy)
        .where(
            ApprovalPolicy.organization_id == context.organization_id,
            ApprovalPolicy.name == payload.name,
            ApprovalPolicy.status == ApprovalPolicyStatus.ACTIVE,
        )
        .order_by(ApprovalPolicy.version.desc())
        .limit(1)
    )
    version = 1 if current is None else current.version + 1
    if current is not None:
        if effective_from <= current.effective_from:
            raise ControlConflictError("New policy must become effective after the current version")
        current.status = ApprovalPolicyStatus.INACTIVE
        current.effective_to = effective_from

    policy = ApprovalPolicy(
        organization_id=context.organization_id,
        name=payload.name,
        version=version,
        status=ApprovalPolicyStatus.ACTIVE,
        minimum_amount=payload.minimum_amount,
        maximum_amount=payload.maximum_amount,
        required_approvals=payload.required_approvals,
        prohibit_self_approval=payload.prohibit_self_approval,
        rules=payload.rules,
        effective_from=effective_from,
        created_by_user_id=context.user_id,
    )
    context.session.add(policy)
    await context.session.flush()
    _audit_and_event(
        context,
        action="approval.policy.created",
        object_type="approval_policy",
        object_id=policy.id,
        object_version=policy.version,
        changes={"name": policy.name, "required_approvals": policy.required_approvals},
    )
    return ApprovalPolicyRead(
        id=policy.id,
        organization_id=policy.organization_id,
        name=policy.name,
        version=policy.version,
        status=policy.status,
        minimum_amount=policy.minimum_amount,
        maximum_amount=policy.maximum_amount,
        required_approvals=policy.required_approvals,
        prohibit_self_approval=policy.prohibit_self_approval,
        rules=policy.rules,
        effective_from=policy.effective_from,
        effective_to=policy.effective_to,
        created_at=policy.created_at,
    )


async def request_requisition_approval(
    context: RequestContext,
    requisition_id: uuid.UUID,
    payload: ApprovalRequestCreate,
) -> ApprovalRequestRead:
    requisition = await context.session.scalar(
        select(Requisition)
        .where(
            Requisition.organization_id == context.organization_id,
            Requisition.id == requisition_id,
        )
        .with_for_update()
    )
    if requisition is None:
        raise ControlNotFoundError("Requisition not found")
    if requisition.version != payload.expected_requisition_version:
        raise ControlConflictError(
            f"Expected requisition version {payload.expected_requisition_version}, "
            f"current version is {requisition.version}"
        )
    if requisition.status is not RequisitionStatus.SUBMITTED:
        raise ControlConflictError("Only submitted requisitions can enter approval")

    budget = await context.session.scalar(
        select(Budget).where(
            Budget.organization_id == context.organization_id,
            Budget.id == payload.budget_id,
        )
    )
    policy = await context.session.scalar(
        select(ApprovalPolicy).where(
            ApprovalPolicy.organization_id == context.organization_id,
            ApprovalPolicy.id == payload.policy_id,
        )
    )
    revision = await context.session.scalar(
        select(RequisitionRevision).where(
            RequisitionRevision.organization_id == context.organization_id,
            RequisitionRevision.requisition_id == requisition.id,
            RequisitionRevision.version == requisition.version,
        )
    )
    if budget is None or policy is None or revision is None:
        raise ControlNotFoundError("Budget, policy, or submitted snapshot not found")
    today = date.today()
    now = datetime.now(UTC)
    if budget.status is not BudgetStatus.ACTIVE or not (
        budget.period_start <= today <= budget.period_end
    ):
        raise ControlValidationError("Budget is not active for the current date")
    if budget.currency != requisition.currency:
        raise ControlValidationError("Budget and requisition currencies must match")
    if policy.status is not ApprovalPolicyStatus.ACTIVE or policy.effective_from > now:
        raise ControlValidationError("Approval policy is not currently effective")

    missing_prices = await context.session.scalar(
        select(func.count(RequisitionLine.id)).where(
            RequisitionLine.organization_id == context.organization_id,
            RequisitionLine.requisition_id == requisition.id,
            RequisitionLine.estimated_unit_price.is_(None),
        )
    )
    if missing_prices:
        raise ControlValidationError("Every line needs an estimated price before approval")
    amount = await context.session.scalar(
        select(func.sum(RequisitionLine.quantity * RequisitionLine.estimated_unit_price)).where(
            RequisitionLine.organization_id == context.organization_id,
            RequisitionLine.requisition_id == requisition.id,
        )
    )
    requested_amount = Decimal(amount or 0).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_EVEN)
    if requested_amount <= ZERO:
        raise ControlValidationError("Approval amount must be positive")
    if requested_amount < policy.minimum_amount or (
        policy.maximum_amount is not None and requested_amount > policy.maximum_amount
    ):
        raise ControlValidationError("Requisition amount is outside the approval policy range")

    existing = await context.session.scalar(
        select(ApprovalRequest.id).where(
            ApprovalRequest.organization_id == context.organization_id,
            ApprovalRequest.requisition_id == requisition.id,
            ApprovalRequest.requisition_version == requisition.version,
        )
    )
    if existing is not None:
        raise ControlConflictError("An approval request already exists for this version")

    request = ApprovalRequest(
        organization_id=context.organization_id,
        requisition_id=requisition.id,
        requisition_version=requisition.version,
        snapshot_digest=revision.content_digest,
        budget_id=budget.id,
        policy_id=policy.id,
        policy_version=policy.version,
        requested_amount=requested_amount,
        currency=requisition.currency,
        required_approvals=policy.required_approvals,
        approval_count=0,
        prohibit_self_approval=policy.prohibit_self_approval,
        policy_snapshot={
            "id": str(policy.id),
            "name": policy.name,
            "version": policy.version,
            "required_approvals": policy.required_approvals,
            "prohibit_self_approval": policy.prohibit_self_approval,
            "rules": policy.rules,
        },
        status=ApprovalRequestStatus.PENDING,
        requested_by_user_id=context.user_id,
    )
    context.session.add(request)
    await context.session.flush()
    _audit_and_event(
        context,
        action="approval.requested",
        object_type="approval_request",
        object_id=request.id,
        object_version=1,
        changes={
            "requisition_id": str(requisition.id),
            "requested_amount": str(requested_amount),
        },
    )
    return await read_approval_request(context, request.id)


async def read_approval_request(
    context: RequestContext, approval_request_id: uuid.UUID
) -> ApprovalRequestRead:
    request = await context.session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.organization_id == context.organization_id,
            ApprovalRequest.id == approval_request_id,
        )
    )
    if request is None:
        raise ControlNotFoundError("Approval request not found")
    decisions = list(
        await context.session.scalars(
            select(ApprovalDecision)
            .where(
                ApprovalDecision.organization_id == context.organization_id,
                ApprovalDecision.approval_request_id == request.id,
            )
            .order_by(ApprovalDecision.decided_at, ApprovalDecision.id)
        )
    )
    return ApprovalRequestRead(
        id=request.id,
        organization_id=request.organization_id,
        requisition_id=request.requisition_id,
        requisition_version=request.requisition_version,
        snapshot_digest=request.snapshot_digest,
        budget_id=request.budget_id,
        policy_id=request.policy_id,
        policy_version=request.policy_version,
        requested_amount=request.requested_amount,
        currency=request.currency,
        required_approvals=request.required_approvals,
        approval_count=request.approval_count,
        prohibit_self_approval=request.prohibit_self_approval,
        status=request.status,
        requested_by_user_id=request.requested_by_user_id,
        completed_at=request.completed_at,
        created_at=request.created_at,
        updated_at=request.updated_at,
        decisions=[
            ApprovalDecisionRead(
                id=decision.id,
                approver_user_id=decision.approver_user_id,
                decision=decision.decision,
                comment=decision.comment,
                decided_at=decision.decided_at,
            )
            for decision in decisions
        ],
    )


async def decide_approval(
    context: RequestContext,
    approval_request_id: uuid.UUID,
    decision_value: ApprovalDecisionValue,
    payload: ApprovalDecisionWrite,
) -> ApprovalRequestRead:
    request = await context.session.scalar(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.organization_id == context.organization_id,
            ApprovalRequest.id == approval_request_id,
        )
        .with_for_update()
    )
    if request is None:
        raise ControlNotFoundError("Approval request not found")
    if request.status is not ApprovalRequestStatus.PENDING:
        raise ControlConflictError(f"Approval request is already {request.status.value}")
    requisition = await context.session.scalar(
        select(Requisition)
        .where(
            Requisition.organization_id == context.organization_id,
            Requisition.id == request.requisition_id,
        )
        .with_for_update()
    )
    if requisition is None:
        raise ControlNotFoundError("Requisition not found")
    if (
        requisition.version != request.requisition_version
        or requisition.status is not RequisitionStatus.SUBMITTED
    ):
        raise ControlConflictError("Requisition changed after approval was requested")
    if (
        decision_value is ApprovalDecisionValue.APPROVE
        and request.prohibit_self_approval
        and requisition.created_by_user_id == context.user_id
    ):
        raise ControlValidationError("Requester cannot approve their own requisition")
    existing = await context.session.scalar(
        select(ApprovalDecision.id).where(
            ApprovalDecision.organization_id == context.organization_id,
            ApprovalDecision.approval_request_id == request.id,
            ApprovalDecision.approver_user_id == context.user_id,
        )
    )
    if existing is not None:
        raise ControlConflictError("Approver has already decided this request")

    now = datetime.now(UTC)
    context.session.add(
        ApprovalDecision(
            organization_id=context.organization_id,
            approval_request_id=request.id,
            approver_user_id=context.user_id,
            decision=decision_value,
            comment=payload.comment.strip() if payload.comment else None,
            decided_at=now,
        )
    )
    event_version = request.approval_count + 1
    if decision_value is ApprovalDecisionValue.REJECT:
        request.status = ApprovalRequestStatus.REJECTED
        request.completed_at = now
        requisition.status = RequisitionStatus.REJECTED
        requisition.version += 1
        _audit_and_event(
            context,
            action="approval.rejected",
            object_type="approval_request",
            object_id=request.id,
            object_version=event_version,
            changes={"requisition_id": str(requisition.id)},
        )
        _audit_and_event(
            context,
            action="requisition.rejected",
            object_type="requisition",
            object_id=requisition.id,
            object_version=requisition.version,
            changes={"approval_request_id": str(request.id)},
        )
    else:
        request.approval_count += 1
        if request.approval_count >= request.required_approvals:
            await _finalize_approval(context, request, requisition, now)
        else:
            _audit_and_event(
                context,
                action="approval.decision.recorded",
                object_type="approval_request",
                object_id=request.id,
                object_version=event_version,
                changes={"approval_count": request.approval_count},
            )
    await context.session.flush()
    return await read_approval_request(context, request.id)


async def _finalize_approval(
    context: RequestContext,
    request: ApprovalRequest,
    requisition: Requisition,
    now: datetime,
) -> None:
    budget = await context.session.scalar(
        select(Budget)
        .where(
            Budget.organization_id == context.organization_id,
            Budget.id == request.budget_id,
        )
        .with_for_update()
    )
    if budget is None:
        raise ControlNotFoundError("Budget not found")
    if budget.status is not BudgetStatus.ACTIVE:
        raise ControlValidationError("Budget is not active")
    today = date.today()
    if not budget.period_start <= today <= budget.period_end:
        raise ControlValidationError("Budget is outside its active period")
    available, _, _, _ = await _budget_balances(context, budget.id)
    if available < request.requested_amount:
        raise ControlValidationError(
            f"Insufficient available budget: {available} {budget.currency}"
        )

    budget.version += 1
    context.session.add_all(
        [
            BudgetLedgerEntry(
                organization_id=context.organization_id,
                budget_id=budget.id,
                requisition_id=requisition.id,
                entry_type=BudgetEntryType.RESERVATION,
                delta_available=-request.requested_amount,
                delta_reserved=request.requested_amount,
                delta_committed=ZERO,
                delta_consumed=ZERO,
                idempotency_key=f"approval:{request.id}:reservation",
                reference_type="approval_request",
                reference_id=request.id,
                reason="Reserve budget for approved requisition",
                actor_user_id=context.user_id,
                occurred_at=now,
            ),
            BudgetReservation(
                organization_id=context.organization_id,
                budget_id=budget.id,
                requisition_id=requisition.id,
                approval_request_id=request.id,
                amount=request.requested_amount,
            ),
        ]
    )
    request.status = ApprovalRequestStatus.APPROVED
    request.completed_at = now
    requisition.status = RequisitionStatus.APPROVED
    requisition.version += 1
    _audit_and_event(
        context,
        action="budget.reserved",
        object_type="budget",
        object_id=budget.id,
        object_version=budget.version,
        changes={
            "approval_request_id": str(request.id),
            "amount": str(request.requested_amount),
        },
    )
    _audit_and_event(
        context,
        action="approval.approved",
        object_type="approval_request",
        object_id=request.id,
        object_version=request.approval_count,
        changes={"requisition_id": str(requisition.id)},
    )
    _audit_and_event(
        context,
        action="requisition.approved",
        object_type="requisition",
        object_id=requisition.id,
        object_version=requisition.version,
        changes={"approval_request_id": str(request.id)},
    )
