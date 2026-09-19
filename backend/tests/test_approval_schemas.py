from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.approvals import ApprovalPolicyCreate, BudgetCreate


def test_budget_rejects_invalid_period() -> None:
    with pytest.raises(ValidationError, match="period_end"):
        BudgetCreate(
            code="IT-2026",
            name="IT equipment",
            period_start=date(2026, 12, 31),
            period_end=date(2026, 1, 1),
            initial_allocation=Decimal("1000000"),
        )


def test_policy_rejects_inverted_amount_range() -> None:
    with pytest.raises(ValidationError, match="maximum_amount"):
        ApprovalPolicyCreate(
            name="Standard procurement",
            minimum_amount=Decimal("1000"),
            maximum_amount=Decimal("100"),
        )


def test_policy_accepts_versionable_control_fields() -> None:
    policy = ApprovalPolicyCreate(
        name="Standard procurement",
        minimum_amount=Decimal("0"),
        maximum_amount=Decimal("30000000"),
        required_approvals=2,
        prohibit_self_approval=True,
        effective_from=datetime(2026, 9, 19, tzinfo=UTC),
    )
    assert policy.required_approvals == 2
    assert policy.prohibit_self_approval is True
