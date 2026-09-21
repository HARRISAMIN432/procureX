from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.commercial import AfterSalesCaseCreate, ClosureCreate, SupportCaseCreate


def test_closure_requires_explicit_confirmation() -> None:
    with pytest.raises(ValidationError):
        ClosureCreate(reason="The organization is no longer operating", confirmation="close")


def test_support_case_rejects_too_short_description() -> None:
    with pytest.raises(ValidationError):
        SupportCaseCreate(subject="Help", description="short")


def test_after_sales_case_accepts_controlled_case_types() -> None:
    case = AfterSalesCaseCreate(
        purchase_order_id=uuid4(),
        case_type="credit_request",
        description="Supplier issued a credit for rejected units.",
        financial_impact=Decimal("125.50"),
    )
    assert case.case_type == "credit_request"
