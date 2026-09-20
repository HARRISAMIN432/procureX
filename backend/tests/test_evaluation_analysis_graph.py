from langgraph.checkpoint.memory import InMemorySaver

from app.ai.evaluation import (
    GroundedComparisonSummary,
    ModelGeneration,
    SupplierNarrative,
)
from app.graphs.evaluation_analysis import build_evaluation_analysis_graph
from app.services.evaluation_evidence import AuthorizedEvidence


def evidence(anchor_id: str, submission_id: str) -> AuthorizedEvidence:
    return AuthorizedEvidence(
        evidence_anchor_id=anchor_id,
        submission_id=submission_id,
        document_version_id="document-1",
        page_number=1,
        field_key="delivery",
        field_label="Delivery",
        verified_value="14 days",
        quoted_text="Delivery within fourteen days.",
    )


async def test_analysis_graph_generates_and_validates_grounded_summary() -> None:
    passages = [evidence("anchor-1", "submission-1")]

    async def load(_: str, __: str, requested: set[str] | None) -> list[AuthorizedEvidence]:
        if requested is None:
            return passages
        return [item for item in passages if item.evidence_anchor_id in requested]

    async def generate(_: dict[str, object]) -> ModelGeneration:
        return ModelGeneration(
            summary=GroundedComparisonSummary(
                executive_summary="Submission 1 offers verified fourteen-day delivery.",
                executive_summary_evidence_anchor_ids=["anchor-1"],
                supplier_narratives=[
                    SupplierNarrative(
                        submission_id="submission-1",
                        narrative="The verified delivery term is fourteen days.",
                        evidence_anchor_ids=["anchor-1"],
                    )
                ],
            ),
            provider="gemini",
            model="gemini-3.1-pro-preview",
            prompt_version="test-v1",
            input_tokens=10,
            output_tokens=20,
            latency_ms=5,
            provider_request_id="request-1",
        )

    graph = build_evaluation_analysis_graph(load, generate, InMemorySaver())
    result = await graph.ainvoke(
        {
            "organization_id": "00000000-0000-0000-0000-000000000001",
            "evaluation_id": "00000000-0000-0000-0000-000000000002",
            "analysis_run_id": "00000000-0000-0000-0000-000000000003",
            "source_digest": "a" * 64,
            "submission_ids": ["submission-1"],
            "unresolved_finding_ids": [],
            "status": "running",
        },
        {"configurable": {"thread_id": "grounded-summary"}},
    )

    assert result["status"] == "completed"
    assert result["citations_validated"] is True
    assert result["comparison_summary"]["executive_summary_evidence_anchor_ids"] == ["anchor-1"]


async def test_analysis_graph_rejects_cross_submission_citation() -> None:
    passages = [
        evidence("anchor-1", "submission-1"),
        evidence("anchor-2", "submission-2"),
    ]

    async def load(_: str, __: str, requested: set[str] | None) -> list[AuthorizedEvidence]:
        if requested is None:
            return passages
        return [item for item in passages if item.evidence_anchor_id in requested]

    async def generate(_: dict[str, object]) -> ModelGeneration:
        return ModelGeneration(
            summary=GroundedComparisonSummary(
                executive_summary="Two submissions were compared.",
                executive_summary_evidence_anchor_ids=["anchor-1", "anchor-2"],
                supplier_narratives=[
                    SupplierNarrative(
                        submission_id="submission-1",
                        narrative="Unsupported use of submission 2 evidence.",
                        evidence_anchor_ids=["anchor-2"],
                    ),
                    SupplierNarrative(
                        submission_id="submission-2",
                        narrative="Submission 2 delivery.",
                        evidence_anchor_ids=["anchor-2"],
                    ),
                ],
            ),
            provider="gemini",
            model="gemini-3.1-pro-preview",
            prompt_version="test-v1",
            input_tokens=10,
            output_tokens=20,
            latency_ms=5,
            provider_request_id=None,
        )

    graph = build_evaluation_analysis_graph(load, generate, InMemorySaver())
    try:
        await graph.ainvoke(
            {
                "organization_id": "00000000-0000-0000-0000-000000000001",
                "evaluation_id": "00000000-0000-0000-0000-000000000002",
                "analysis_run_id": "00000000-0000-0000-0000-000000000003",
                "source_digest": "a" * 64,
                "submission_ids": ["submission-1", "submission-2"],
                "unresolved_finding_ids": [],
                "status": "running",
            },
            {"configurable": {"thread_id": "cross-submission"}},
        )
    except ValueError as exc:
        assert "another submission" in str(exc)
    else:
        raise AssertionError("Expected cross-submission evidence to be rejected")
