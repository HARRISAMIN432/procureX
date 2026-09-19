from typing import Any, Literal, TypedDict

from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import interrupt


class EvaluationGraphState(TypedDict):
    organization_id: str
    evaluation_id: str
    source_digest: str
    unresolved_finding_ids: list[str]
    citations_validated: bool
    status: str


def validate_evidence(state: EvaluationGraphState) -> dict[str, str]:
    if not state["source_digest"] or not state["evaluation_id"]:
        raise ValueError("Evaluation state is missing immutable source identifiers")
    if not state["citations_validated"]:
        raise ValueError("Evaluation citations must be validated before finalization")
    return {"status": "evidence_validated"}


def route_findings(state: EvaluationGraphState) -> Literal["human_review", "finalize"]:
    return "human_review" if state["unresolved_finding_ids"] else "finalize"


def human_review(state: EvaluationGraphState) -> dict[str, str]:
    response: Any = interrupt(
        {
            "kind": "evaluation_finding_review",
            "evaluation_id": state["evaluation_id"],
            "source_digest": state["source_digest"],
            "unresolved_finding_ids": state["unresolved_finding_ids"],
        }
    )
    if not isinstance(response, dict) or response.get("review_complete") is not True:
        raise ValueError("Review resume must confirm completion")
    if response.get("source_digest") != state["source_digest"]:
        raise ValueError("Review resume source digest is stale")
    return {"status": "review_confirmed"}


def finalize(_: EvaluationGraphState) -> dict[str, str]:
    return {"status": "completed"}


def build_evaluation_graph(checkpointer: Any = None) -> Any:
    builder = StateGraph(EvaluationGraphState)
    builder.add_node("validate_evidence", validate_evidence)
    builder.add_node("human_review", human_review)
    builder.add_node("finalize", finalize)  # type: ignore[arg-type]
    builder.add_edge(START, "validate_evidence")
    builder.add_conditional_edges("validate_evidence", route_findings)
    builder.add_edge("human_review", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer, name="evaluation_graph")
