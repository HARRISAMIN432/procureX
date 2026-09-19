import uuid
from decimal import Decimal
from types import SimpleNamespace

from app.models.evaluations import OfferEligibility, RequirementOutcome
from app.services.evaluations import (
    build_grounded_summary,
    calculate_landed_cost,
    calculate_preferred_ratio,
    calculate_scores,
    determine_eligibility,
    evaluation_snapshot_digest,
)


def test_landed_cost_uses_exact_decimal_arithmetic() -> None:
    lines = [
        SimpleNamespace(
            quantity=Decimal("2.5000"),
            unit_price=Decimal("10.1234"),
            tax_amount=Decimal("1.0000"),
            freight_amount=Decimal("0.5000"),
        ),
        SimpleNamespace(
            quantity=Decimal("1.0000"),
            unit_price=Decimal("3.3333"),
            tax_amount=Decimal("0"),
            freight_amount=Decimal("0"),
        ),
    ]
    assert calculate_landed_cost(lines) == Decimal("30.1418")


def test_mandatory_outcomes_control_eligibility() -> None:
    assert determine_eligibility([(True, RequirementOutcome.PASS)]) is OfferEligibility.ELIGIBLE
    assert determine_eligibility([(True, RequirementOutcome.UNKNOWN)]) is OfferEligibility.BLOCKED
    assert (
        determine_eligibility([(True, RequirementOutcome.UNKNOWN), (True, RequirementOutcome.FAIL)])
        is OfferEligibility.INELIGIBLE
    )
    assert (
        determine_eligibility([(True, RequirementOutcome.NOT_APPLICABLE)])
        is OfferEligibility.BLOCKED
    )


def test_preferred_ratio_excludes_not_applicable() -> None:
    ratio = calculate_preferred_ratio(
        [
            (False, RequirementOutcome.PASS),
            (False, RequirementOutcome.FAIL),
            (False, RequirementOutcome.NOT_APPLICABLE),
            (True, RequirementOutcome.PASS),
        ]
    )
    assert ratio == Decimal("0.500000")


def test_weighted_scores_are_deterministic_and_exclude_blocked_offers() -> None:
    first, second, blocked = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    scores = calculate_scores(
        [
            (first, OfferEligibility.ELIGIBLE, Decimal("100"), Decimal("1")),
            (second, OfferEligibility.ELIGIBLE, Decimal("200"), Decimal("0.5")),
            (blocked, OfferEligibility.BLOCKED, Decimal("50"), Decimal("1")),
        ],
        Decimal("0.8"),
        Decimal("0.2"),
    )
    assert scores[first] == Decimal("100.0000")
    assert scores[second] == Decimal("50.0000")
    assert scores[blocked] is None


def test_snapshot_digest_is_order_independent_for_object_keys() -> None:
    assert evaluation_snapshot_digest({"a": 1, "b": 2}) == evaluation_snapshot_digest(
        {"b": 2, "a": 1}
    )


def test_grounded_summary_reports_only_deterministic_snapshot_facts() -> None:
    offers = [
        {
            "submission_id": "submission-1",
            "eligibility": "eligible",
            "score": "90.0000",
            "checks": [{"evidence_anchor_ids": ["anchor-1"]}],
        },
        {
            "submission_id": "submission-2",
            "eligibility": "blocked",
            "score": None,
            "checks": [{"evidence_anchor_ids": []}],
        },
    ]
    assert build_grounded_summary(offers) == {
        "offer_count": 2,
        "eligible_count": 1,
        "blocked_count": 1,
        "ineligible_count": 0,
        "leading_submission_id": "submission-1",
        "cited_evidence_anchor_ids": ["anchor-1"],
        "basis": "deterministic_evaluation_snapshot",
    }
