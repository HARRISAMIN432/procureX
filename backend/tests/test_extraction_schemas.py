from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.extractions import ExtractedFieldStatus, ReviewAction
from app.schemas.extractions import ExtractionResultCreate, FieldReviewCreate


def proposed_field() -> dict[str, object]:
    return {
        "field_key": "commercial.total",
        "label": "Total",
        "data_type": "money",
        "raw_value": "PKR 100.00",
        "normalized_value": {"currency": "PKR", "amount": "100.00"},
        "status": ExtractedFieldStatus.PROPOSED,
        "is_critical": True,
        "confidence": "0.9500",
        "anchors": [{"page_number": 1, "quoted_text": "Total: PKR 100.00"}],
    }


def test_extracted_value_requires_evidence_anchor() -> None:
    field = proposed_field()
    field["anchors"] = []
    with pytest.raises(ValidationError, match="evidence anchor"):
        ExtractionResultCreate(
            parse_id=uuid4(),
            result_key="extract-run-1",
            schema_name="supplier_quote",
            schema_version="1",
            fields=[field],
        )


def test_extraction_cannot_claim_preverified_field() -> None:
    field = proposed_field()
    field["status"] = ExtractedFieldStatus.VERIFIED
    with pytest.raises(ValidationError, match="pre-verify"):
        ExtractionResultCreate(
            parse_id=uuid4(),
            result_key="extract-run-1",
            schema_name="supplier_quote",
            schema_version="1",
            fields=[field],
        )


def test_missing_field_cannot_claim_value_or_evidence() -> None:
    field = proposed_field()
    field["status"] = ExtractedFieldStatus.MISSING
    with pytest.raises(ValidationError, match="Missing fields cannot contain values"):
        ExtractionResultCreate(
            parse_id=uuid4(),
            result_key="extract-run-1",
            schema_name="supplier_quote",
            schema_version="1",
            fields=[field],
        )


def test_extraction_field_keys_are_unique() -> None:
    field = proposed_field()
    with pytest.raises(ValidationError, match="field_key values must be unique"):
        ExtractionResultCreate(
            parse_id=uuid4(),
            result_key="extract-run-1",
            schema_name="supplier_quote",
            schema_version="1",
            fields=[field, field],
        )


def test_correction_requires_normalized_value() -> None:
    with pytest.raises(ValidationError, match="requires normalized_value"):
        FieldReviewCreate(
            expected_revision=1,
            action=ReviewAction.CORRECT,
            reason="Source value was OCRed incorrectly",
        )
