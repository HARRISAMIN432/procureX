import hashlib
import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from sqlalchemy import func, select

from app.auth.context import RequestContext
from app.models.evaluations import (
    Evaluation,
    EvaluationStatus,
    OfferEligibility,
    OfferEvaluation,
    RequirementCheck,
    RequirementCheckEvidence,
    RequirementOutcome,
)
from app.models.extractions import (
    EvidenceAnchor,
    ExtractedField,
    ExtractedFieldStatus,
    Extraction,
    ExtractionStatus,
)
from app.models.platform import ActorType, AuditEvent, OutboxEvent
from app.models.sourcing import (
    QuoteLine,
    QuoteSubmission,
    QuoteSubmissionDocument,
    Rfq,
    RfqRequirement,
    RfqStatus,
    SubmissionStatus,
)
from app.schemas.evaluations import (
    EvaluationCreate,
    EvaluationRead,
    OfferAssessmentWrite,
    OfferEvaluationRead,
    RequirementCheckRead,
)

MONEY_QUANTUM = Decimal("0.0001")
RATIO_QUANTUM = Decimal("0.000001")
SCORE_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True)
class PreparedOffer:
    input: OfferAssessmentWrite
    submission: QuoteSubmission
    landed_cost: Decimal
    eligibility: OfferEligibility
    preferred_ratio: Decimal


class EvaluationNotFoundError(ValueError):
    pass


class EvaluationConflictError(ValueError):
    pass


class EvaluationValidationError(ValueError):
    pass


def calculate_landed_cost(lines: Iterable[QuoteLine]) -> Decimal:
    total = sum(
        (line.quantity * line.unit_price + line.tax_amount + line.freight_amount for line in lines),
        Decimal("0"),
    )
    return total.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def determine_eligibility(
    checks: Iterable[tuple[bool, RequirementOutcome]],
) -> OfferEligibility:
    mandatory = [outcome for is_mandatory, outcome in checks if is_mandatory]
    if RequirementOutcome.FAIL in mandatory:
        return OfferEligibility.INELIGIBLE
    if any(
        outcome in {RequirementOutcome.UNKNOWN, RequirementOutcome.NOT_APPLICABLE}
        for outcome in mandatory
    ):
        return OfferEligibility.BLOCKED
    return OfferEligibility.ELIGIBLE


def calculate_preferred_ratio(
    checks: Iterable[tuple[bool, RequirementOutcome]],
) -> Decimal:
    applicable = [
        outcome
        for is_mandatory, outcome in checks
        if not is_mandatory and outcome is not RequirementOutcome.NOT_APPLICABLE
    ]
    if not applicable:
        return Decimal("0").quantize(RATIO_QUANTUM)
    passed = sum(outcome is RequirementOutcome.PASS for outcome in applicable)
    return (Decimal(passed) / Decimal(len(applicable))).quantize(
        RATIO_QUANTUM, rounding=ROUND_HALF_UP
    )


def calculate_scores(
    offers: Iterable[tuple[uuid.UUID, OfferEligibility, Decimal, Decimal]],
    price_weight: Decimal,
    preferred_weight: Decimal,
) -> dict[uuid.UUID, Decimal | None]:
    offers = list(offers)
    eligible_costs = [
        cost for _, eligibility, cost, _ in offers if eligibility is OfferEligibility.ELIGIBLE
    ]
    lowest_cost = min(eligible_costs) if eligible_costs else None
    scores: dict[uuid.UUID, Decimal | None] = {}
    for offer_id, eligibility, landed_cost, preferred_ratio in offers:
        if eligibility is not OfferEligibility.ELIGIBLE or lowest_cost is None:
            scores[offer_id] = None
            continue
        if landed_cost == 0:
            price_ratio = Decimal("1")
        else:
            price_ratio = lowest_cost / landed_cost
        score = Decimal("100") * (price_weight * price_ratio + preferred_weight * preferred_ratio)
        scores[offer_id] = score.quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)
    return scores


def evaluation_snapshot_digest(snapshot: dict[str, object]) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def build_grounded_summary(offers: list[dict[str, object]]) -> dict[str, object]:
    eligible = [offer for offer in offers if offer["eligibility"] == "eligible"]
    blocked = [offer for offer in offers if offer["eligibility"] == "blocked"]
    ineligible = [offer for offer in offers if offer["eligibility"] == "ineligible"]
    ranked = sorted(
        (offer for offer in eligible if offer["score"] is not None),
        key=lambda offer: (-Decimal(str(offer["score"])), str(offer["submission_id"])),
    )
    cited_anchor_ids: set[str] = set()
    for offer in offers:
        for check in cast(list[dict[str, object]], offer["checks"]):
            cited_anchor_ids.update(cast(list[str], check["evidence_anchor_ids"]))
    return {
        "offer_count": len(offers),
        "eligible_count": len(eligible),
        "blocked_count": len(blocked),
        "ineligible_count": len(ineligible),
        "leading_submission_id": ranked[0]["submission_id"] if ranked else None,
        "cited_evidence_anchor_ids": sorted(cited_anchor_ids),
        "basis": "deterministic_evaluation_snapshot",
    }


async def create_evaluation(
    context: RequestContext, rfq_id: uuid.UUID, payload: EvaluationCreate
) -> EvaluationRead:
    rfq = await context.session.scalar(
        select(Rfq)
        .where(Rfq.organization_id == context.organization_id, Rfq.id == rfq_id)
        .with_for_update()
    )
    if rfq is None:
        raise EvaluationNotFoundError("RFQ not found")
    if rfq.version != payload.expected_rfq_version:
        raise EvaluationConflictError(
            f"Expected RFQ version {payload.expected_rfq_version}, current version is {rfq.version}"
        )
    if rfq.status is not RfqStatus.CLOSED:
        raise EvaluationConflictError("Only a closed RFQ can be evaluated")

    requirements = list(
        await context.session.scalars(
            select(RfqRequirement)
            .where(
                RfqRequirement.organization_id == context.organization_id,
                RfqRequirement.rfq_id == rfq.id,
            )
            .order_by(RfqRequirement.id)
        )
    )
    if not requirements:
        raise EvaluationValidationError("RFQ has no controlled requirements")
    requirement_by_id = {requirement.id: requirement for requirement in requirements}
    required_ids = set(requirement_by_id)

    submission_ids = [offer.submission_id for offer in payload.offers]
    submissions = list(
        await context.session.scalars(
            select(QuoteSubmission).where(
                QuoteSubmission.organization_id == context.organization_id,
                QuoteSubmission.rfq_id == rfq.id,
                QuoteSubmission.status == SubmissionStatus.SUBMITTED,
            )
        )
    )
    if not submissions:
        raise EvaluationValidationError("RFQ has no current submitted quote versions")
    if set(submission_ids) != {submission.id for submission in submissions}:
        raise EvaluationValidationError(
            "Every current submitted quote version must be evaluated exactly once"
        )
    submission_by_id = {submission.id: submission for submission in submissions}
    if any(submission.currency != rfq.currency for submission in submissions):
        raise EvaluationValidationError("Every quote currency must match the RFQ currency")

    requested_anchor_ids = {
        anchor_id
        for offer in payload.offers
        for check in offer.checks
        for anchor_id in check.evidence_anchor_ids
    }
    valid_evidence_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    if requested_anchor_ids:
        evidence_rows = await context.session.execute(
            select(EvidenceAnchor.id, QuoteSubmissionDocument.submission_id)
            .join(
                ExtractedField,
                (ExtractedField.organization_id == EvidenceAnchor.organization_id)
                & (ExtractedField.extraction_id == EvidenceAnchor.extraction_id)
                & (ExtractedField.id == EvidenceAnchor.field_id),
            )
            .join(
                Extraction,
                (Extraction.organization_id == ExtractedField.organization_id)
                & (Extraction.id == ExtractedField.extraction_id),
            )
            .join(
                QuoteSubmissionDocument,
                (QuoteSubmissionDocument.organization_id == EvidenceAnchor.organization_id)
                & (
                    QuoteSubmissionDocument.document_version_id
                    == EvidenceAnchor.document_version_id
                ),
            )
            .where(
                EvidenceAnchor.organization_id == context.organization_id,
                EvidenceAnchor.id.in_(requested_anchor_ids),
                ExtractedField.status == ExtractedFieldStatus.VERIFIED,
                Extraction.status == ExtractionStatus.COMPLETED,
            )
        )
        valid_evidence_pairs = set(evidence_rows.tuples())
        for offer in payload.offers:
            for check in offer.checks:
                if any(
                    (anchor_id, offer.submission_id) not in valid_evidence_pairs
                    for anchor_id in check.evidence_anchor_ids
                ):
                    raise EvaluationValidationError(
                        "Evidence must be a verified anchor from a completed extraction "
                        "attached to the assessed quote"
                    )

    lines = list(
        await context.session.scalars(
            select(QuoteLine).where(
                QuoteLine.organization_id == context.organization_id,
                QuoteLine.rfq_id == rfq.id,
                QuoteLine.submission_id.in_(submission_ids),
            )
        )
    )
    lines_by_submission: dict[uuid.UUID, list[QuoteLine]] = {
        submission_id: [] for submission_id in submission_ids
    }
    for line in lines:
        lines_by_submission[line.submission_id].append(line)
    if any(not offer_lines for offer_lines in lines_by_submission.values()):
        raise EvaluationValidationError("Every evaluated quote must contain at least one line")

    prepared: list[PreparedOffer] = []
    for offer_input in payload.offers:
        assessed_ids = {check.requirement_id for check in offer_input.checks}
        if assessed_ids != required_ids:
            raise EvaluationValidationError(
                "Every offer must assess every RFQ requirement exactly once"
            )
        submission = submission_by_id[offer_input.submission_id]
        checks = [
            (
                requirement_by_id[check.requirement_id].priority == "mandatory",
                check.outcome,
            )
            for check in offer_input.checks
        ]
        prepared.append(
            PreparedOffer(
                input=offer_input,
                submission=submission,
                landed_cost=calculate_landed_cost(lines_by_submission[submission.id]),
                eligibility=determine_eligibility(checks),
                preferred_ratio=calculate_preferred_ratio(checks),
            )
        )

    offer_ids = {item.submission.id: uuid.uuid4() for item in prepared}
    scores = calculate_scores(
        (
            (
                offer_ids[item.submission.id],
                item.eligibility,
                item.landed_cost,
                item.preferred_ratio,
            )
            for item in prepared
        ),
        payload.scoring_policy.price_weight,
        payload.scoring_policy.preferred_weight,
    )
    snapshot_offers: list[dict[str, object]] = []
    for item in sorted(prepared, key=lambda value: str(value.submission.id)):
        submission = item.submission
        offer_input = item.input
        offer_id = offer_ids[submission.id]
        snapshot_offers.append(
            {
                "submission_id": str(submission.id),
                "submission_digest": submission.content_digest,
                "supplier_id": str(submission.supplier_id),
                "landed_cost": str(item.landed_cost),
                "eligibility": item.eligibility.value,
                "preferred_ratio": str(item.preferred_ratio),
                "score": str(scores[offer_id]) if scores[offer_id] is not None else None,
                "checks": [
                    {
                        "requirement_id": str(check.requirement_id),
                        "outcome": check.outcome.value,
                        "rationale": check.rationale,
                        "evidence_anchor_ids": sorted(
                            str(anchor_id) for anchor_id in check.evidence_anchor_ids
                        ),
                    }
                    for check in sorted(
                        offer_input.checks, key=lambda value: str(value.requirement_id)
                    )
                ],
            }
        )
    snapshot: dict[str, object] = {
        "rfq_id": str(rfq.id),
        "source_rfq_version": rfq.version,
        "publication_number": rfq.publication_number,
        "currency": rfq.currency,
        "scoring_policy": payload.scoring_policy.model_dump(mode="json"),
        "offers": snapshot_offers,
        "summary": build_grounded_summary(snapshot_offers),
    }
    digest = evaluation_snapshot_digest(snapshot)
    current_version = await context.session.scalar(
        select(func.max(Evaluation.version)).where(
            Evaluation.organization_id == context.organization_id,
            Evaluation.rfq_id == rfq.id,
        )
    )
    evaluation = Evaluation(
        id=uuid.uuid4(),
        organization_id=context.organization_id,
        rfq_id=rfq.id,
        version=(current_version or 0) + 1,
        source_rfq_version=rfq.version,
        publication_number=rfq.publication_number,
        currency=rfq.currency,
        status=EvaluationStatus.COMPLETED,
        scoring_policy=payload.scoring_policy.model_dump(mode="json"),
        snapshot=snapshot,
        content_digest=digest,
        created_by_user_id=context.user_id,
    )
    context.session.add(evaluation)
    await context.session.flush()
    for item in prepared:
        submission = item.submission
        offer_input = item.input
        offer_id = offer_ids[submission.id]
        context.session.add(
            OfferEvaluation(
                id=offer_id,
                organization_id=context.organization_id,
                rfq_id=rfq.id,
                evaluation_id=evaluation.id,
                submission_id=submission.id,
                supplier_id=submission.supplier_id,
                eligibility=item.eligibility,
                landed_cost=item.landed_cost,
                preferred_ratio=item.preferred_ratio,
                score=scores[offer_id],
            )
        )
        for check in offer_input.checks:
            requirement_check = RequirementCheck(
                id=uuid.uuid4(),
                organization_id=context.organization_id,
                rfq_id=rfq.id,
                evaluation_id=evaluation.id,
                offer_evaluation_id=offer_id,
                rfq_requirement_id=check.requirement_id,
                outcome=check.outcome,
                is_mandatory=(requirement_by_id[check.requirement_id].priority == "mandatory"),
                rationale=check.rationale,
            )
            context.session.add(requirement_check)
            context.session.add_all(
                [
                    RequirementCheckEvidence(
                        organization_id=context.organization_id,
                        evaluation_id=evaluation.id,
                        requirement_check_id=requirement_check.id,
                        evidence_anchor_id=anchor_id,
                    )
                    for anchor_id in check.evidence_anchor_ids
                ]
            )
    context.session.add_all(
        [
            AuditEvent(
                organization_id=context.organization_id,
                actor_type=ActorType.USER,
                actor_id=context.user_id,
                action="evaluation.completed",
                object_type="evaluation",
                object_id=evaluation.id,
                object_version=evaluation.version,
                changes={"rfq_id": str(rfq.id), "content_digest": digest},
            ),
            OutboxEvent(
                organization_id=context.organization_id,
                aggregate_type="evaluation",
                aggregate_id=evaluation.id,
                aggregate_version=evaluation.version,
                event_type="evaluation.completed",
                schema_version=1,
                payload={
                    "evaluation_id": str(evaluation.id),
                    "rfq_id": str(rfq.id),
                    "version": evaluation.version,
                    "content_digest": digest,
                },
                actor_id=context.user_id,
            ),
        ]
    )
    await context.session.flush()
    return await read_evaluation(context, evaluation.id)


async def read_evaluation(context: RequestContext, evaluation_id: uuid.UUID) -> EvaluationRead:
    evaluation = await context.session.scalar(
        select(Evaluation).where(
            Evaluation.organization_id == context.organization_id,
            Evaluation.id == evaluation_id,
        )
    )
    if evaluation is None:
        raise EvaluationNotFoundError("Evaluation not found")
    offers = list(
        await context.session.scalars(
            select(OfferEvaluation)
            .where(
                OfferEvaluation.organization_id == context.organization_id,
                OfferEvaluation.evaluation_id == evaluation.id,
            )
            .order_by(OfferEvaluation.submission_id)
        )
    )
    checks = list(
        await context.session.scalars(
            select(RequirementCheck)
            .where(
                RequirementCheck.organization_id == context.organization_id,
                RequirementCheck.evaluation_id == evaluation.id,
            )
            .order_by(RequirementCheck.rfq_requirement_id)
        )
    )
    evidence_rows = await context.session.execute(
        select(
            RequirementCheckEvidence.requirement_check_id,
            RequirementCheckEvidence.evidence_anchor_id,
        )
        .where(
            RequirementCheckEvidence.organization_id == context.organization_id,
            RequirementCheckEvidence.evaluation_id == evaluation.id,
        )
        .order_by(RequirementCheckEvidence.evidence_anchor_id)
    )
    evidence_by_check: dict[uuid.UUID, list[uuid.UUID]] = {check.id: [] for check in checks}
    for check_id, anchor_id in evidence_rows.tuples():
        evidence_by_check[check_id].append(anchor_id)
    checks_by_offer: dict[uuid.UUID, list[RequirementCheck]] = {offer.id: [] for offer in offers}
    for check in checks:
        checks_by_offer[check.offer_evaluation_id].append(check)
    return EvaluationRead(
        id=evaluation.id,
        rfq_id=evaluation.rfq_id,
        version=evaluation.version,
        source_rfq_version=evaluation.source_rfq_version,
        publication_number=evaluation.publication_number,
        currency=evaluation.currency,
        status=evaluation.status,
        scoring_policy=evaluation.scoring_policy,
        content_digest=evaluation.content_digest,
        summary=evaluation.snapshot.get("summary", {}),
        created_at=evaluation.created_at,
        offers=[
            OfferEvaluationRead(
                id=offer.id,
                submission_id=offer.submission_id,
                supplier_id=offer.supplier_id,
                eligibility=offer.eligibility,
                landed_cost=offer.landed_cost,
                preferred_ratio=offer.preferred_ratio,
                score=offer.score,
                checks=[
                    RequirementCheckRead(
                        id=check.id,
                        rfq_requirement_id=check.rfq_requirement_id,
                        outcome=check.outcome,
                        is_mandatory=check.is_mandatory,
                        rationale=check.rationale,
                        evidence_anchor_ids=evidence_by_check[check.id],
                    )
                    for check in checks_by_offer[offer.id]
                ],
            )
            for offer in offers
        ],
    )
