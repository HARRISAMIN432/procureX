from typing import Any, Literal, TypedDict

from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.types import interrupt


class DocumentAnalysisState(TypedDict):
    organization_id: str
    document_version_id: str
    parse_id: str
    extraction_id: str
    source_digest: str
    unresolved_critical_field_ids: list[str]
    status: str


def prepare_review(state: DocumentAnalysisState) -> dict[str, str]:
    if not state["source_digest"] or not state["extraction_id"]:
        raise ValueError("Document analysis state is missing immutable source identifiers")
    return {"status": "awaiting_review"}


def route_review(state: DocumentAnalysisState) -> Literal["human_review", "finalize"]:
    return "human_review" if state["unresolved_critical_field_ids"] else "finalize"


def human_review(state: DocumentAnalysisState) -> dict[str, str]:
    response: Any = interrupt(
        {
            "kind": "document_field_review",
            "extraction_id": state["extraction_id"],
            "source_digest": state["source_digest"],
            "unresolved_critical_field_ids": state["unresolved_critical_field_ids"],
        }
    )
    if not isinstance(response, dict) or response.get("review_complete") is not True:
        raise ValueError("Review resume must confirm completion")
    if response.get("source_digest") != state["source_digest"]:
        raise ValueError("Review resume source digest is stale")
    return {"status": "review_confirmed"}


def finalize(_: DocumentAnalysisState) -> dict[str, str]:
    return {"status": "completed"}


def build_document_analysis_graph(checkpointer: Any = None) -> Any:
    builder = StateGraph(DocumentAnalysisState)
    builder.add_node("prepare_review", prepare_review)
    builder.add_node("human_review", human_review)
    builder.add_node("finalize", finalize)  # type: ignore[arg-type]
    builder.add_edge(START, "prepare_review")
    builder.add_conditional_edges("prepare_review", route_review)
    builder.add_edge("human_review", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer, name="document_analysis_graph")
