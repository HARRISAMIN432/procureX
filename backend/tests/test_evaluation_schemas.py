import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.evaluations import RequirementOutcome
from app.schemas.evaluations import (
    EvaluationCreate,
    OfferAssessmentWrite,
    RequirementAssessmentWrite,
    ScoringPolicy,
)


def check(requirement_id: uuid.UUID | None = None) -> RequirementAssessmentWrite:
    return RequirementAssessmentWrite(
        requirement_id=requirement_id or uuid.uuid4(),
        outcome=RequirementOutcome.PASS,
        rationale="  confirmed by reviewer  ",
    )


def test_scoring_weights_must_total_exactly_one() -> None:
    assert ScoringPolicy(price_weight="0.8", preferred_weight="0.2").price_weight == Decimal("0.8")
    with pytest.raises(ValidationError, match="exactly 1"):
        ScoringPolicy(price_weight="0.8", preferred_weight="0.3")


def test_assessment_normalizes_rationale_and_rejects_duplicate_requirements() -> None:
    requirement_id = uuid.uuid4()
    assessment = check(requirement_id)
    assert assessment.rationale == "confirmed by reviewer"
    with pytest.raises(ValidationError, match="only once"):
        OfferAssessmentWrite(
            submission_id=uuid.uuid4(),
            checks=[assessment, check(requirement_id)],
        )


def test_evaluation_rejects_duplicate_submissions() -> None:
    submission_id = uuid.uuid4()
    offer = OfferAssessmentWrite(submission_id=submission_id, checks=[check()])
    with pytest.raises(ValidationError, match="only once"):
        EvaluationCreate(
            expected_rfq_version=3,
            scoring_policy=ScoringPolicy(price_weight="1", preferred_weight="0"),
            offers=[offer, offer],
        )


def test_assessment_rejects_duplicate_evidence_anchors() -> None:
    anchor_id = uuid.uuid4()
    with pytest.raises(ValidationError, match="evidence anchor"):
        RequirementAssessmentWrite(
            requirement_id=uuid.uuid4(),
            outcome=RequirementOutcome.PASS,
            rationale="confirmed",
            evidence_anchor_ids=[anchor_id, anchor_id],
        )
