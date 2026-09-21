from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.graphs.document_analysis import build_document_analysis_graph


def initial_state() -> dict[str, object]:
    return {
        "organization_id": "org-1",
        "document_version_id": "version-1",
        "parse_id": "parse-1",
        "extraction_id": "extraction-1",
        "source_digest": "a" * 64,
        "unresolved_critical_field_ids": ["field-1"],
        "status": "queued",
    }


def test_document_analysis_graph_interrupts_and_resumes_review() -> None:
    graph = build_document_analysis_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "document-analysis-test"}}

    paused = graph.invoke(initial_state(), config)
    assert paused["status"] == "awaiting_review"
    assert paused["__interrupt__"][0].value["extraction_id"] == "extraction-1"

    completed = graph.invoke(
        Command(resume={"review_complete": True, "source_digest": "a" * 64}), config
    )
    assert completed["status"] == "completed"


def test_document_analysis_graph_rejects_stale_resume() -> None:
    graph = build_document_analysis_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "document-analysis-stale-test"}}
    graph.invoke(initial_state(), config)

    try:
        graph.invoke(Command(resume={"review_complete": True, "source_digest": "b" * 64}), config)
    except ValueError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("Expected stale review resume to fail")
