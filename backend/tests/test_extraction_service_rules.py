from uuid import uuid4

from app.models.extractions import ExtractedField, ExtractedFieldStatus
from app.schemas.extractions import ExtractionResultCreate
from app.services.extractions import extraction_result_digest, unresolved_field_keys


def test_extraction_digest_is_deterministic_and_evidence_bound() -> None:
    payload = ExtractionResultCreate(
        parse_id=uuid4(),
        result_key="extract-run-1",
        schema_name="supplier_quote",
        schema_version="1",
        fields=[
            {
                "field_key": "commercial.currency",
                "label": "Currency",
                "data_type": "currency",
                "raw_value": "PKR",
                "normalized_value": "PKR",
                "status": ExtractedFieldStatus.PROPOSED,
                "is_critical": True,
                "anchors": [{"page_number": 1, "quoted_text": "Currency: PKR"}],
            }
        ],
    )
    same = payload.model_copy(deep=True)
    changed = payload.model_copy(deep=True)
    changed.fields[0].anchors[0].quoted_text = "Currency: USD"

    assert extraction_result_digest(payload) == extraction_result_digest(same)
    assert extraction_result_digest(payload) != extraction_result_digest(changed)


def test_critical_fields_must_be_verified_before_finalization() -> None:
    fields = [
        ExtractedField(
            field_key="critical.rejected",
            status=ExtractedFieldStatus.REJECTED,
            is_critical=True,
        ),
        ExtractedField(
            field_key="optional.rejected",
            status=ExtractedFieldStatus.REJECTED,
            is_critical=False,
        ),
        ExtractedField(
            field_key="critical.verified",
            status=ExtractedFieldStatus.VERIFIED,
            is_critical=True,
        ),
    ]

    assert unresolved_field_keys(fields) == ["critical.rejected"]
