from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.graphs.evaluation import build_evaluation_graph


def initial_state() -> dict[str, object]:
    return {
        "organization_id": "org-1",
        "evaluation_id": "evaluation-1",
        "source_digest": "a" * 64,
        "unresolved_finding_ids": ["finding-1"],
        "citations_validated": True,
        "status": "queued",
    }


def test_evaluation_graph_interrupts_and_resumes_findings() -> None:
    graph = build_evaluation_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "evaluation-test"}}

    paused = graph.invoke(initial_state(), config)
    assert paused["status"] == "evidence_validated"
    assert paused["__interrupt__"][0].value["evaluation_id"] == "evaluation-1"

    completed = graph.invoke(
        Command(resume={"review_complete": True, "source_digest": "a" * 64}), config
    )
    assert completed["status"] == "completed"


def test_evaluation_graph_rejects_unvalidated_citations() -> None:
    graph = build_evaluation_graph(InMemorySaver())
    state = initial_state()
    state["citations_validated"] = False

    try:
        graph.invoke(state, {"configurable": {"thread_id": "invalid-citations"}})
    except ValueError as exc:
        assert "citations" in str(exc)
    else:
        raise AssertionError("Expected unvalidated citations to fail")


def test_evaluation_graph_rejects_stale_resume() -> None:
    graph = build_evaluation_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "stale-evaluation"}}
    graph.invoke(initial_state(), config)

    try:
        graph.invoke(Command(resume={"review_complete": True, "source_digest": "b" * 64}), config)
    except ValueError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("Expected stale review resume to fail")
