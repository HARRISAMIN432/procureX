from collections.abc import Awaitable, Callable
from typing import Any, Literal, TypedDict, cast

from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import interrupt

from app.ai.evaluation import ModelGeneration
from app.services.evaluation_evidence import AuthorizedEvidence


class EvaluationAnalysisState(TypedDict, total=False):
    organization_id: str
    evaluation_id: str
    analysis_run_id: str
    source_digest: str
    submission_ids: list[str]
    unresolved_finding_ids: list[str]
    authorized_evidence_ids: list[str]
    evidence_submission_ids: dict[str, str]
    comparison_summary: dict[str, object]
    model_invocation: dict[str, object]
    citations_validated: bool
    status: str


EvidenceLoader = Callable[[str, str, set[str] | None], Awaitable[list[AuthorizedEvidence]]]
SummaryGenerator = Callable[[dict[str, object]], Awaitable[ModelGeneration]]


def build_evaluation_analysis_graph(
    evidence_loader: EvidenceLoader,
    summary_generator: SummaryGenerator,
    checkpointer: Any,
) -> Any:
    async def retrieve_evidence(state: EvaluationAnalysisState) -> dict[str, object]:
        evidence = await evidence_loader(state["organization_id"], state["evaluation_id"], None)
        if not evidence:
            raise ValueError("No authorized verified evidence is available for this evaluation")
        return {
            "authorized_evidence_ids": [item.evidence_anchor_id for item in evidence],
            "evidence_submission_ids": {
                item.evidence_anchor_id: item.submission_id for item in evidence
            },
            "status": "evidence_retrieved",
        }

    async def draft_summary(state: EvaluationAnalysisState) -> dict[str, object]:
        authorized_ids = set(state["authorized_evidence_ids"])
        evidence = await evidence_loader(
            state["organization_id"], state["evaluation_id"], authorized_ids
        )
        if {item.evidence_anchor_id for item in evidence} != authorized_ids:
            raise ValueError("Authorized evidence changed while the analysis was running")
        generation = await summary_generator(
            {
                "evaluation_id": state["evaluation_id"],
                "source_digest": state["source_digest"],
                "submission_ids": state["submission_ids"],
                "instruction": "Compare the offers without changing deterministic results.",
                "authorized_evidence": [item.as_prompt_record() for item in evidence],
            }
        )
        return {
            "comparison_summary": generation.summary.model_dump(mode="json"),
            "model_invocation": {
                "provider": generation.provider,
                "model": generation.model,
                "prompt_version": generation.prompt_version,
                "input_tokens": generation.input_tokens,
                "output_tokens": generation.output_tokens,
                "latency_ms": generation.latency_ms,
                "provider_request_id": generation.provider_request_id,
            },
            "status": "summary_drafted",
        }

    def validate_citations(state: EvaluationAnalysisState) -> dict[str, object]:
        summary = state["comparison_summary"]
        authorized = set(state["authorized_evidence_ids"])
        ownership = state["evidence_submission_ids"]
        submission_ids = set(state["submission_ids"])
        cited: list[str] = list(cast(list[str], summary["executive_summary_evidence_anchor_ids"]))
        narratives = cast(list[dict[str, object]], summary["supplier_narratives"])
        narrative_submission_ids = [str(item["submission_id"]) for item in narratives]
        if set(narrative_submission_ids) != submission_ids or len(narrative_submission_ids) != len(
            submission_ids
        ):
            raise ValueError("Generated summary must cover every evaluated submission exactly once")
        for item in narratives:
            submission_id = str(item["submission_id"])
            item_citations = cast(list[str], item["evidence_anchor_ids"])
            if any(ownership.get(anchor_id) != submission_id for anchor_id in item_citations):
                raise ValueError("Supplier narrative cites evidence owned by another submission")
            cited.extend(item_citations)
        for item in cast(list[dict[str, object]], summary.get("key_findings", [])):
            cited.extend(cast(list[str], item["evidence_anchor_ids"]))
        if not cited or not set(cited).issubset(authorized):
            raise ValueError("Generated summary contains missing or unauthorized citations")
        return {"citations_validated": True, "status": "citations_validated"}

    def route_findings(
        state: EvaluationAnalysisState,
    ) -> Literal["human_review", "finalize"]:
        return "human_review" if state["unresolved_finding_ids"] else "finalize"

    def human_review(state: EvaluationAnalysisState) -> dict[str, str]:
        response: Any = interrupt(
            {
                "kind": "evaluation_finding_review",
                "evaluation_id": state["evaluation_id"],
                "analysis_run_id": state["analysis_run_id"],
                "source_digest": state["source_digest"],
                "unresolved_finding_ids": state["unresolved_finding_ids"],
            }
        )
        if not isinstance(response, dict) or response.get("review_complete") is not True:
            raise ValueError("Review resume must confirm completion")
        if response.get("source_digest") != state["source_digest"]:
            raise ValueError("Review resume source digest is stale")
        return {"status": "review_confirmed"}

    def finalize(state: EvaluationAnalysisState) -> dict[str, object]:
        if not state.get("citations_validated"):
            raise ValueError("Validated citations are required before finalization")
        return {"status": "completed"}

    builder = StateGraph(EvaluationAnalysisState)
    builder.add_node("retrieve_authorized_evidence", retrieve_evidence)
    builder.add_node("draft_grounded_summary", draft_summary)
    builder.add_node("validate_citations", validate_citations)
    builder.add_node("human_review", human_review)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "retrieve_authorized_evidence")
    builder.add_edge("retrieve_authorized_evidence", "draft_grounded_summary")
    builder.add_edge("draft_grounded_summary", "validate_citations")
    builder.add_conditional_edges("validate_citations", route_findings)
    builder.add_edge("human_review", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer, name="evaluation_graph")
