from app.ai.evaluation import GroundedComparisonSummary, gemini_response_schema


def test_provider_schema_omits_generation_constraints_but_local_model_keeps_them() -> None:
    schema_text = str(gemini_response_schema())

    assert "maxItems" not in schema_text
    assert "maxLength" not in schema_text
    assert GroundedComparisonSummary.model_json_schema()["properties"]["executive_summary"][
        "maxLength"
    ] == 4000
