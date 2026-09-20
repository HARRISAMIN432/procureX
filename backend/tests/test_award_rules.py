import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.awards import AllocationScenarioCreate, AwardCreate
from app.services.awards import AwardValidationError, digest, scaled


def test_allocation_scenario_rejects_duplicate_minimums() -> None:
    submission_id, item_id = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(ValidationError, match="unique"):
        AllocationScenarioCreate(
            name="Baseline",
            expected_evaluation_digest="a" * 64,
            minimum_quantities=[
                {
                    "submission_id": submission_id,
                    "rfq_item_id": item_id,
                    "quantity": "1",
                },
                {
                    "submission_id": submission_id,
                    "rfq_item_id": item_id,
                    "quantity": "2",
                },
            ],
        )


def test_award_requires_policy_bound_recommendation() -> None:
    payload = AwardCreate(
        expected_scenario_digest="b" * 64,
        recommendation="Select the validated lowest-cost allocation.",
        approval_policy_id=uuid.uuid4(),
    )
    assert payload.approval_policy_id is not None


def test_canonical_digest_is_key_order_independent() -> None:
    assert digest({"a": 1, "b": 2}) == digest({"b": 2, "a": 1})


def test_scaling_rejects_unsupported_precision() -> None:
    assert scaled(Decimal("1.2345"), Decimal("10000")) == 12345
    with pytest.raises(AwardValidationError, match="precision"):
        scaled(Decimal("1.23456"), Decimal("10000"))
