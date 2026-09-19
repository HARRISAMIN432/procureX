from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.requisitions import RequirementPriority, RequirementSource
from app.schemas.requisitions import RequisitionCreate, RequisitionLineWrite


def valid_line(line_number: int = 1) -> RequisitionLineWrite:
    return RequisitionLineWrite(
        line_number=line_number,
        description="Laptop computer",
        quantity=Decimal("10"),
        unit="each",
        estimated_unit_price=Decimal("250000.00"),
    )


def test_requisition_accepts_structured_lines_and_requirements() -> None:
    payload = RequisitionCreate(
        title="Developer laptops",
        justification="Replace unsupported equipment",
        need_by_date=date.today() + timedelta(days=30),
        lines=[valid_line()],
        requirements=[
            {
                "line_number": 1,
                "priority": RequirementPriority.MANDATORY,
                "criterion": "At least 32 GB RAM",
                "verification_method": "Confirm manufacturer specification",
                "source": RequirementSource.HUMAN,
            }
        ],
    )
    assert payload.currency == "PKR"
    assert payload.requirements[0].line_number == 1


def test_requisition_rejects_duplicate_line_numbers() -> None:
    with pytest.raises(ValidationError, match="line_number values must be unique"):
        RequisitionCreate(
            title="Developer laptops",
            justification="Replace unsupported equipment",
            lines=[valid_line(), valid_line()],
        )


def test_requisition_rejects_unknown_requirement_line() -> None:
    with pytest.raises(ValidationError, match="unknown lines"):
        RequisitionCreate(
            title="Developer laptops",
            justification="Replace unsupported equipment",
            lines=[valid_line()],
            requirements=[
                {
                    "line_number": 2,
                    "priority": "mandatory",
                    "criterion": "At least 32 GB RAM",
                    "verification_method": "Confirm manufacturer specification",
                }
            ],
        )


def test_requisition_rejects_past_need_date() -> None:
    with pytest.raises(ValidationError, match="cannot be in the past"):
        RequisitionCreate(
            title="Developer laptops",
            justification="Replace unsupported equipment",
            need_by_date=date.today() - timedelta(days=1),
        )
