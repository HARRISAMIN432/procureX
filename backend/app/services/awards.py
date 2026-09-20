import hashlib
import json
import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from sqlalchemy import func, select

from app.auth.context import RequestContext
from app.models.ai import AnalysisRun, AnalysisRunStatus
from app.models.approvals import ApprovalPolicy, ApprovalPolicyStatus
from app.models.awards import (
    AllocationLine,
    AllocationScenario,
    AllocationStatus,
    Award,
    AwardDecision,
    AwardDecisionValue,
    AwardStatus,
)
from app.models.evaluations import Evaluation, OfferEligibility, OfferEvaluation
from app.models.platform import ActorType, AuditEvent, OutboxEvent
from app.models.sourcing import QuoteLine, QuoteSubmission, RfqItem, SubmissionStatus
from app.models.suppliers import Supplier, SupplierStatus
from app.optimization.allocation import AllocationProblem, Demand, Offer, solve_allocation
from app.schemas.awards import (
    AllocationLineRead,
    AllocationScenarioCreate,
    AllocationScenarioList,
    AllocationScenarioRead,
    AwardCreate,
    AwardDecisionRead,
    AwardDecisionWrite,
    AwardRead,
    AwardSubmit,
)

QTY_SCALE = Decimal("10000")
MONEY_SCALE = Decimal("10000")
OBJECTIVE_SCALE = QTY_SCALE * MONEY_SCALE
MONEY_QUANTUM = Decimal("0.0001")


class AwardNotFoundError(ValueError):
    pass


class AwardConflictError(ValueError):
    pass


class AwardValidationError(ValueError):
    pass


def digest(value: dict[str, object]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(payload).hexdigest()


def scaled(value: Decimal, scale: Decimal) -> int:
    converted = value * scale
    if converted != converted.to_integral_value():
        raise AwardValidationError(f"Value {value} exceeds supported precision")
    return int(converted)


def unscaled(value: int | None, scale: Decimal) -> Decimal | None:
    if value is None:
        return None
    return (Decimal(value) / scale).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


async def _scenario_read(
    context: RequestContext, scenario: AllocationScenario
) -> AllocationScenarioRead:
    lines = list(
        await context.session.scalars(
            select(AllocationLine)
            .where(
                AllocationLine.organization_id == context.organization_id,
                AllocationLine.scenario_id == scenario.id,
            )
            .order_by(AllocationLine.rfq_item_id, AllocationLine.submission_id)
        )
    )
    return AllocationScenarioRead(
        id=scenario.id,
        evaluation_id=scenario.evaluation_id,
        version=scenario.version,
        name=scenario.name,
        status=scenario.status,
        currency=scenario.currency,
        source_evaluation_digest=scenario.source_evaluation_digest,
        content_digest=scenario.content_digest,
        objective_amount=scenario.objective_amount,
        best_bound_amount=scenario.best_bound_amount,
        relative_gap=scenario.relative_gap,
        runtime_ms=scenario.runtime_ms,
        independently_validated=scenario.independently_validated,
        constraints=scenario.constraints,
        constraint_checks=cast(dict[str, bool], scenario.snapshot.get("constraint_checks", {})),
        infeasibility_reasons=cast(list[str], scenario.snapshot.get("infeasibility_reasons", [])),
        allocations=[
            AllocationLineRead(
                submission_id=line.submission_id,
                supplier_id=line.supplier_id,
                rfq_item_id=line.rfq_item_id,
                quantity=line.quantity,
                unit_cost=line.unit_cost,
                extended_cost=line.extended_cost,
            )
            for line in lines
        ],
        created_at=scenario.created_at,
    )


async def create_allocation_scenario(
    context: RequestContext, evaluation_id: uuid.UUID, payload: AllocationScenarioCreate
) -> AllocationScenarioRead:
    evaluation = await context.session.scalar(
        select(Evaluation)
        .where(
            Evaluation.organization_id == context.organization_id, Evaluation.id == evaluation_id
        )
        .with_for_update()
    )
    if evaluation is None:
        raise AwardNotFoundError("Evaluation not found")
    if evaluation.content_digest != payload.expected_evaluation_digest:
        raise AwardConflictError("Evaluation digest is stale")
    items = list(
        await context.session.scalars(
            select(RfqItem).where(
                RfqItem.organization_id == context.organization_id,
                RfqItem.rfq_id == evaluation.rfq_id,
            )
        )
    )
    eligible = list(
        await context.session.scalars(
            select(OfferEvaluation).where(
                OfferEvaluation.organization_id == context.organization_id,
                OfferEvaluation.evaluation_id == evaluation.id,
                OfferEvaluation.eligibility == OfferEligibility.ELIGIBLE,
            )
        )
    )
    if not eligible:
        raise AwardValidationError("Evaluation has no eligible offers")
    submission_ids = [offer.submission_id for offer in eligible]
    submissions = list(
        await context.session.scalars(
            select(QuoteSubmission).where(
                QuoteSubmission.organization_id == context.organization_id,
                QuoteSubmission.id.in_(submission_ids),
                QuoteSubmission.status == SubmissionStatus.SUBMITTED,
                QuoteSubmission.valid_until >= date.today(),
            )
        )
    )
    submission_by_id = {submission.id: submission for submission in submissions}
    approved_supplier_ids = set(
        await context.session.scalars(
            select(Supplier.id).where(
                Supplier.organization_id == context.organization_id,
                Supplier.id.in_([submission.supplier_id for submission in submissions]),
                Supplier.status == SupplierStatus.APPROVED,
            )
        )
    )
    item_by_id = {item.id: item for item in items}
    quote_lines = list(
        await context.session.scalars(
            select(QuoteLine).where(
                QuoteLine.organization_id == context.organization_id,
                QuoteLine.submission_id.in_(submission_by_id),
            )
        )
    )
    minimums = {
        (item.submission_id, item.rfq_item_id): item.quantity for item in payload.minimum_quantities
    }
    solver_offers: list[Offer] = []
    offer_metadata: dict[tuple[str, str], tuple[uuid.UUID, Decimal]] = {}
    for line in quote_lines:
        submission = submission_by_id[line.submission_id]
        if submission.supplier_id not in approved_supplier_ids:
            continue
        if line.is_alternative and not item_by_id[line.rfq_item_id].alternatives_allowed:
            continue
        capacity = scaled(line.quantity, QTY_SCALE)
        landed_unit_cost = line.unit_price + (line.tax_amount + line.freight_amount) / line.quantity
        unit_cost = scaled(landed_unit_cost, MONEY_SCALE)
        minimum = scaled(
            minimums.get((line.submission_id, line.rfq_item_id), Decimal("0.0001")), QTY_SCALE
        )
        solver_offers.append(
            Offer(
                str(line.rfq_item_id),
                str(line.submission_id),
                str(submission.supplier_id),
                capacity,
                minimum,
                unit_cost,
            )
        )
        offer_metadata[(str(line.rfq_item_id), str(line.submission_id))] = (
            submission.supplier_id,
            landed_unit_cost.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP),
        )
    accepted_offer_keys = {
        (uuid.UUID(offer.submission_id), uuid.UUID(offer.item_id)) for offer in solver_offers
    }
    unknown_minimums = set(minimums) - accepted_offer_keys
    if unknown_minimums:
        raise AwardValidationError(
            "Minimum quantity overrides must reference eligible current offer lines"
        )
    accepted_supplier_ids = {uuid.UUID(offer.supplier_id) for offer in solver_offers}
    if set(payload.fixed_supplier_costs) - accepted_supplier_ids:
        raise AwardValidationError(
            "Fixed supplier costs must reference suppliers with eligible current offers"
        )
    constraints = payload.model_dump(mode="json")
    problem = AllocationProblem(
        demands=tuple(Demand(str(item.id), scaled(item.quantity, QTY_SCALE)) for item in items),
        offers=tuple(solver_offers),
        fixed_supplier_costs={
            str(key): scaled(value, OBJECTIVE_SCALE)
            for key, value in payload.fixed_supplier_costs.items()
        },
        budget=scaled(payload.budget_amount, OBJECTIVE_SCALE) if payload.budget_amount else None,
        maximum_suppliers=payload.maximum_suppliers,
        allow_split_awards=payload.allow_split_awards,
        timeout_seconds=payload.timeout_seconds,
    )
    result = solve_allocation(problem)
    allocation_snapshot: list[dict[str, object]] = []
    for solved_line in result.allocations:
        supplier_id, landed_cost = offer_metadata[(solved_line.item_id, solved_line.submission_id)]
        quantity = Decimal(solved_line.quantity) / QTY_SCALE
        allocation_snapshot.append(
            {
                "rfq_item_id": solved_line.item_id,
                "submission_id": solved_line.submission_id,
                "supplier_id": str(supplier_id),
                "quantity": str(quantity),
                "unit_cost": str(landed_cost),
                "extended_cost": str((quantity * landed_cost).quantize(MONEY_QUANTUM)),
            }
        )
    snapshot: dict[str, object] = {
        "evaluation_id": str(evaluation.id),
        "evaluation_digest": evaluation.content_digest,
        "submissions": [
            {
                "submission_id": str(submission.id),
                "supplier_id": str(submission.supplier_id),
                "content_digest": submission.content_digest,
            }
            for submission in sorted(submissions, key=lambda value: str(value.id))
        ],
        "constraints": constraints,
        "solver_status": result.outcome.value,
        "allocations": allocation_snapshot,
        "constraint_checks": result.constraint_checks,
        "infeasibility_reasons": list(result.infeasibility_reasons),
    }
    content_digest = digest(snapshot)
    version = (
        await context.session.scalar(
            select(func.max(AllocationScenario.version)).where(
                AllocationScenario.organization_id == context.organization_id,
                AllocationScenario.evaluation_id == evaluation.id,
            )
        )
        or 0
    ) + 1
    scenario = AllocationScenario(
        organization_id=context.organization_id,
        rfq_id=evaluation.rfq_id,
        evaluation_id=evaluation.id,
        version=version,
        name=payload.name,
        source_evaluation_digest=evaluation.content_digest,
        status=AllocationStatus(result.outcome.value),
        currency=evaluation.currency,
        constraints=constraints,
        snapshot=snapshot,
        content_digest=content_digest,
        objective_amount=unscaled(result.objective, OBJECTIVE_SCALE),
        best_bound_amount=unscaled(result.best_bound, OBJECTIVE_SCALE),
        relative_gap=Decimal(str(result.relative_gap)) if result.relative_gap is not None else None,
        runtime_ms=result.runtime_ms,
        independently_validated=bool(result.constraint_checks)
        and all(result.constraint_checks.values()),
        created_by_user_id=context.user_id,
    )
    context.session.add(scenario)
    await context.session.flush()
    for snapshot_line in allocation_snapshot:
        context.session.add(
            AllocationLine(
                organization_id=context.organization_id,
                rfq_id=evaluation.rfq_id,
                scenario_id=scenario.id,
                submission_id=uuid.UUID(str(snapshot_line["submission_id"])),
                supplier_id=uuid.UUID(str(snapshot_line["supplier_id"])),
                rfq_item_id=uuid.UUID(str(snapshot_line["rfq_item_id"])),
                quantity=Decimal(str(snapshot_line["quantity"])),
                unit_cost=Decimal(str(snapshot_line["unit_cost"])),
                extended_cost=Decimal(str(snapshot_line["extended_cost"])),
            )
        )
    _event(
        context,
        "allocation.scenario_created",
        "allocation_scenario",
        scenario.id,
        version,
        {
            "evaluation_id": str(evaluation.id),
            "status": scenario.status.value,
            "content_digest": content_digest,
        },
    )
    await context.session.flush()
    return await _scenario_read(context, scenario)


async def list_allocation_scenarios(
    context: RequestContext, evaluation_id: uuid.UUID
) -> AllocationScenarioList:
    scenarios = list(
        await context.session.scalars(
            select(AllocationScenario)
            .where(
                AllocationScenario.organization_id == context.organization_id,
                AllocationScenario.evaluation_id == evaluation_id,
            )
            .order_by(AllocationScenario.version)
        )
    )
    return AllocationScenarioList(
        items=[await _scenario_read(context, item) for item in scenarios], total=len(scenarios)
    )


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


async def _award_read(context: RequestContext, award: Award) -> AwardRead:
    decisions = list(
        await context.session.scalars(
            select(AwardDecision)
            .where(
                AwardDecision.organization_id == context.organization_id,
                AwardDecision.award_id == award.id,
            )
            .order_by(AwardDecision.decided_at)
        )
    )
    return AwardRead(
        id=award.id,
        rfq_id=award.rfq_id,
        evaluation_id=award.evaluation_id,
        allocation_scenario_id=award.allocation_scenario_id,
        version=award.version,
        status=award.status,
        currency=award.currency,
        total_amount=award.total_amount,
        recommendation=award.recommendation,
        dossier=award.dossier,
        snapshot=award.snapshot,
        content_digest=award.content_digest,
        required_approvals=award.required_approvals,
        approval_count=award.approval_count,
        prohibit_self_approval=award.prohibit_self_approval,
        decisions=[
            AwardDecisionRead(
                approver_user_id=item.approver_user_id,
                decision=item.decision,
                comment=item.comment,
                decided_at=item.decided_at,
            )
            for item in decisions
        ],
        created_at=award.created_at,
        submitted_at=award.submitted_at,
        completed_at=award.completed_at,
    )


async def create_award(
    context: RequestContext, scenario_id: uuid.UUID, payload: AwardCreate
) -> AwardRead:
    scenario = await context.session.scalar(
        select(AllocationScenario)
        .where(
            AllocationScenario.organization_id == context.organization_id,
            AllocationScenario.id == scenario_id,
        )
        .with_for_update()
    )
    if scenario is None:
        raise AwardNotFoundError("Allocation scenario not found")
    if scenario.content_digest != payload.expected_scenario_digest:
        raise AwardConflictError("Allocation scenario digest is stale")
    if (
        scenario.status not in {AllocationStatus.OPTIMAL, AllocationStatus.FEASIBLE}
        or not scenario.independently_validated
    ):
        raise AwardValidationError(
            "Only an independently validated feasible scenario can become an award"
        )
    policy = await context.session.scalar(
        select(ApprovalPolicy).where(
            ApprovalPolicy.organization_id == context.organization_id,
            ApprovalPolicy.id == payload.approval_policy_id,
            ApprovalPolicy.status == ApprovalPolicyStatus.ACTIVE,
            ApprovalPolicy.effective_from <= datetime.now(UTC),
        )
    )
    if policy is None:
        raise AwardValidationError("An active approval policy is required")
    now = datetime.now(UTC)
    if policy.effective_to is not None and policy.effective_to <= now:
        raise AwardValidationError("The approval policy is no longer effective")
    total_amount = scenario.objective_amount or Decimal("0")
    if total_amount < policy.minimum_amount or (
        policy.maximum_amount is not None and total_amount > policy.maximum_amount
    ):
        raise AwardValidationError("Award amount is outside the approval policy range")
    analysis_run: AnalysisRun | None = None
    if payload.analysis_run_id is not None:
        analysis_run = await context.session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.organization_id == context.organization_id,
                AnalysisRun.id == payload.analysis_run_id,
                AnalysisRun.evaluation_id == scenario.evaluation_id,
                AnalysisRun.status == AnalysisRunStatus.COMPLETED,
                AnalysisRun.source_digest == scenario.source_evaluation_digest,
            )
        )
        if analysis_run is None or analysis_run.output is None:
            raise AwardValidationError(
                "Analysis run must be completed, current, and belong to the evaluation"
            )
    version = (
        await context.session.scalar(
            select(func.max(Award.version)).where(
                Award.organization_id == context.organization_id, Award.rfq_id == scenario.rfq_id
            )
        )
        or 0
    ) + 1
    dossier = {
        "evaluation_id": str(scenario.evaluation_id),
        "evaluation_digest": scenario.source_evaluation_digest,
        "allocation_scenario_id": str(scenario.id),
        "allocation_digest": scenario.content_digest,
        "analysis_run_id": str(analysis_run.id) if analysis_run else None,
        "constraint_checks": scenario.snapshot.get("constraint_checks", {}),
        "approval_policy": {
            "id": str(policy.id),
            "version": policy.version,
            "required_approvals": policy.required_approvals,
            "prohibit_self_approval": policy.prohibit_self_approval,
            "rules": policy.rules,
        },
    }
    selected_ids = {
        item["submission_id"]
        for item in cast(list[dict[str, object]], scenario.snapshot["allocations"])
    }
    selected_submissions = [
        item
        for item in cast(list[dict[str, object]], scenario.snapshot["submissions"])
        if item["submission_id"] in selected_ids
    ]
    snapshot = {
        "dossier": dossier,
        "recommendation": payload.recommendation,
        "allocations": scenario.snapshot["allocations"],
        "submissions": selected_submissions,
        "currency": scenario.currency,
        "required_approvals": policy.required_approvals,
        "prohibit_self_approval": policy.prohibit_self_approval,
    }
    award = Award(
        organization_id=context.organization_id,
        rfq_id=scenario.rfq_id,
        evaluation_id=scenario.evaluation_id,
        allocation_scenario_id=scenario.id,
        version=version,
        status=AwardStatus.DRAFT,
        currency=scenario.currency,
        total_amount=total_amount,
        recommendation=payload.recommendation,
        dossier=dossier,
        snapshot=snapshot,
        content_digest=digest(snapshot),
        required_approvals=policy.required_approvals,
        approval_count=0,
        prohibit_self_approval=policy.prohibit_self_approval,
        created_by_user_id=context.user_id,
    )
    context.session.add(award)
    await context.session.flush()
    _event(
        context,
        "award.created",
        "award",
        award.id,
        award.version,
        {"rfq_id": str(award.rfq_id), "content_digest": award.content_digest},
    )
    return await _award_read(context, award)


async def read_award(context: RequestContext, award_id: uuid.UUID) -> AwardRead:
    award = await context.session.scalar(
        select(Award).where(Award.organization_id == context.organization_id, Award.id == award_id)
    )
    if award is None:
        raise AwardNotFoundError("Award not found")
    return await _award_read(context, award)


async def submit_award(
    context: RequestContext, award_id: uuid.UUID, payload: AwardSubmit
) -> AwardRead:
    award = await _locked_award(context, award_id, payload.expected_content_digest)
    if award.status is not AwardStatus.DRAFT:
        raise AwardConflictError("Only a draft award can be submitted")
    if not await _ensure_current(context, award):
        return await _award_read(context, award)
    award.status = AwardStatus.PENDING_APPROVAL
    award.submitted_at = datetime.now(UTC)
    _event(
        context,
        "award.submitted",
        "award",
        award.id,
        award.version,
        {"content_digest": award.content_digest},
    )
    return await _award_read(context, award)


async def decide_award(
    context: RequestContext,
    award_id: uuid.UUID,
    decision: AwardDecisionValue,
    payload: AwardDecisionWrite,
) -> AwardRead:
    award = await _locked_award(context, award_id, payload.expected_content_digest)
    if award.status is not AwardStatus.PENDING_APPROVAL:
        raise AwardConflictError("Award is not pending approval")
    if (
        decision is AwardDecisionValue.APPROVE
        and award.prohibit_self_approval
        and award.created_by_user_id == context.user_id
    ):
        raise AwardValidationError("Award preparer cannot approve this recommendation")
    if await context.session.scalar(
        select(AwardDecision.id).where(
            AwardDecision.organization_id == context.organization_id,
            AwardDecision.award_id == award.id,
            AwardDecision.approver_user_id == context.user_id,
        )
    ):
        raise AwardConflictError("User already decided this award")
    if not await _ensure_current(context, award):
        return await _award_read(context, award)
    now = datetime.now(UTC)
    context.session.add(
        AwardDecision(
            organization_id=context.organization_id,
            award_id=award.id,
            approver_user_id=context.user_id,
            decision=decision,
            comment=payload.comment.strip() if payload.comment else None,
            decided_at=now,
        )
    )
    if decision is AwardDecisionValue.REJECT:
        award.status = AwardStatus.REJECTED
        award.completed_at = now
    else:
        award.approval_count += 1
        if award.approval_count >= award.required_approvals:
            award.status = AwardStatus.APPROVED
            award.completed_at = now
    _event(
        context,
        f"award.{decision.value}",
        "award",
        award.id,
        award.version,
        {"approval_count": award.approval_count, "status": award.status.value},
    )
    await context.session.flush()
    return await _award_read(context, award)


async def _locked_award(
    context: RequestContext, award_id: uuid.UUID, expected_digest: str
) -> Award:
    award = await context.session.scalar(
        select(Award)
        .where(Award.organization_id == context.organization_id, Award.id == award_id)
        .with_for_update()
    )
    if award is None:
        raise AwardNotFoundError("Award not found")
    if award.content_digest != expected_digest:
        raise AwardConflictError("Award digest is stale")
    return award


async def _ensure_current(context: RequestContext, award: Award) -> bool:
    evaluation = await context.session.scalar(
        select(Evaluation).where(
            Evaluation.organization_id == context.organization_id,
            Evaluation.id == award.evaluation_id,
        )
    )
    scenario = await context.session.scalar(
        select(AllocationScenario).where(
            AllocationScenario.organization_id == context.organization_id,
            AllocationScenario.id == award.allocation_scenario_id,
        )
    )
    if (
        evaluation is None
        or scenario is None
        or evaluation.content_digest != str(award.dossier["evaluation_digest"])
        or scenario.content_digest != str(award.dossier["allocation_digest"])
    ):
        award.status = AwardStatus.STALE
        award.completed_at = datetime.now(UTC)
        _event(
            context,
            "award.stale",
            "award",
            award.id,
            award.version,
            {"reason": "source_digest_changed"},
        )
        return False
    policy_snapshot = cast(dict[str, object], award.dossier["approval_policy"])
    policy = await context.session.scalar(
        select(ApprovalPolicy).where(
            ApprovalPolicy.organization_id == context.organization_id,
            ApprovalPolicy.id == uuid.UUID(str(policy_snapshot["id"])),
            ApprovalPolicy.version == int(str(policy_snapshot["version"])),
            ApprovalPolicy.status == ApprovalPolicyStatus.ACTIVE,
        )
    )
    now = datetime.now(UTC)
    if (
        policy is None
        or policy.effective_from > now
        or (policy.effective_to is not None and policy.effective_to <= now)
    ):
        award.status = AwardStatus.STALE
        award.completed_at = now
        _event(
            context,
            "award.stale",
            "award",
            award.id,
            award.version,
            {"reason": "approval_policy_changed"},
        )
        return False
    analysis_run_id = award.dossier.get("analysis_run_id")
    if analysis_run_id is not None:
        analysis_run = await context.session.scalar(
            select(AnalysisRun).where(
                AnalysisRun.organization_id == context.organization_id,
                AnalysisRun.id == uuid.UUID(str(analysis_run_id)),
                AnalysisRun.evaluation_id == award.evaluation_id,
                AnalysisRun.status == AnalysisRunStatus.COMPLETED,
                AnalysisRun.source_digest == evaluation.content_digest,
            )
        )
        if analysis_run is None:
            award.status = AwardStatus.STALE
            award.completed_at = now
            _event(
                context,
                "award.stale",
                "award",
                award.id,
                award.version,
                {"reason": "analysis_run_changed"},
            )
            return False
    submissions = cast(list[dict[str, object]], award.snapshot["submissions"])
    for source in submissions:
        submission = await context.session.scalar(
            select(QuoteSubmission).where(
                QuoteSubmission.organization_id == context.organization_id,
                QuoteSubmission.id == uuid.UUID(str(source["submission_id"])),
            )
        )
        supplier = await context.session.scalar(
            select(Supplier).where(
                Supplier.organization_id == context.organization_id,
                Supplier.id == uuid.UUID(str(source["supplier_id"])),
            )
        )
        if (
            submission is None
            or submission.status is not SubmissionStatus.SUBMITTED
            or submission.valid_until < date.today()
            or submission.content_digest != source["content_digest"]
            or supplier is None
            or supplier.status is not SupplierStatus.APPROVED
        ):
            award.status = AwardStatus.STALE
            award.completed_at = datetime.now(UTC)
            _event(
                context,
                "award.stale",
                "award",
                award.id,
                award.version,
                {"reason": "supplier_or_submission_changed"},
            )
            return False
    return True
