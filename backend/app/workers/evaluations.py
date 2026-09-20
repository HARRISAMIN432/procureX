import asyncio
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from sqlalchemy import select

from app.ai.evaluation import PROMPT_VERSION, GeminiComparisonModel
from app.core.config import get_settings
from app.core.database import close_database, tenant_transaction
from app.graphs.evaluation_analysis import build_evaluation_analysis_graph
from app.models.ai import AnalysisRun, AnalysisRunStatus, InvocationStatus, ModelInvocation
from app.models.evaluations import Evaluation, RequirementCheck, RequirementOutcome
from app.models.platform import Job, JobStatus
from app.services.evaluation_evidence import retrieve_authorized_evidence
from app.workers.celery_app import celery_app


def enqueue_evaluation_analysis(organization_id: uuid.UUID, job_id: uuid.UUID) -> None:
    run_evaluation_analysis.apply_async(args=[str(organization_id), str(job_id)])


async def _execute(organization_id: uuid.UUID, job_id: uuid.UUID) -> dict[str, object]:
    settings = get_settings()
    async with tenant_transaction(organization_id) as session:
        job = await session.scalar(
            select(Job)
            .where(Job.organization_id == organization_id, Job.id == job_id)
            .with_for_update()
        )
        if job is None:
            raise ValueError("Evaluation analysis job not found")
        if job.status is JobStatus.COMPLETED:
            return job.result or {"status": "completed"}
        if job.status in {JobStatus.CANCELLED, JobStatus.FAILED}:
            raise ValueError(f"Evaluation analysis job is {job.status.value}")
        run_id = uuid.UUID(str(job.payload["analysis_run_id"]))
        run = await session.scalar(
            select(AnalysisRun)
            .where(
                AnalysisRun.organization_id == organization_id,
                AnalysisRun.id == run_id,
            )
            .with_for_update()
        )
        if run is None or run.evaluation_id is None:
            raise ValueError("Evaluation analysis run not found")
        evaluation = await session.scalar(
            select(Evaluation).where(
                Evaluation.organization_id == organization_id,
                Evaluation.id == run.evaluation_id,
            )
        )
        if evaluation is None:
            raise ValueError("Evaluation not found")
        if evaluation.content_digest != run.source_digest:
            run.status = AnalysisRunStatus.STALE
            job.status = JobStatus.FAILED
            job.error_code = "stale_source"
            job.error_detail = "Evaluation digest changed before execution"
            run.error_code = "stale_source"
            run.error_detail = job.error_detail
            run.completed_at = datetime.now(UTC)
            job.completed_at = datetime.now(UTC)
            return {"analysis_run_id": str(run.id), "status": "stale"}
        job.status = JobStatus.RUNNING
        job.attempts += 1
        job.started_at = datetime.now(UTC)
        job.error_code = None
        job.error_detail = None
        run.status = AnalysisRunStatus.RUNNING
        run.started_at = run.started_at or datetime.now(UTC)
        evaluation_id = run.evaluation_id
        thread_id = run.thread_id
        source_digest = run.source_digest
        graph_run_id = run.id
        resume_payload = cast(dict[str, object] | None, job.payload.get("resume"))
        snapshot_offers = cast(list[dict[str, object]], evaluation.snapshot["offers"])
        submission_ids = [str(item["submission_id"]) for item in snapshot_offers]
        unresolved = list(
            await session.scalars(
                select(RequirementCheck.id).where(
                    RequirementCheck.organization_id == organization_id,
                    RequirementCheck.evaluation_id == evaluation_id,
                    RequirementCheck.outcome == RequirementOutcome.UNKNOWN,
                )
            )
        )

    async def evidence_loader(
        org_id: str, eval_id: str, requested_ids: set[str] | None
    ) -> list[Any]:
        if uuid.UUID(org_id) != organization_id or uuid.UUID(eval_id) != evaluation_id:
            raise ValueError("Graph requested evidence outside its authorized scope")
        ids = {uuid.UUID(value) for value in requested_ids} if requested_ids is not None else None
        async with tenant_transaction(organization_id) as evidence_session:
            return await retrieve_authorized_evidence(
                evidence_session,
                organization_id,
                evaluation_id,
                limit=settings.evaluation_evidence_limit,
                max_chars=settings.evaluation_evidence_max_chars,
                anchor_ids=ids,
            )

    async def record_failure(exc: Exception) -> None:
        async with tenant_transaction(organization_id) as failure_session:
            failed_job = await failure_session.scalar(
                select(Job)
                .where(Job.organization_id == organization_id, Job.id == job_id)
                .with_for_update()
            )
            failed_run = await failure_session.scalar(
                select(AnalysisRun)
                .where(
                    AnalysisRun.organization_id == organization_id,
                    AnalysisRun.id == graph_run_id,
                )
                .with_for_update()
            )
            if failed_job is not None:
                exhausted = failed_job.attempts >= failed_job.max_attempts
                failed_job.status = JobStatus.FAILED if exhausted else JobStatus.RETRY_SCHEDULED
                failed_job.error_code = type(exc).__name__[:100]
                failed_job.error_detail = str(exc)[:4000]
            if failed_run is not None and (
                failed_job is None or failed_job.attempts >= failed_job.max_attempts
            ):
                failed_run.status = AnalysisRunStatus.FAILED
                failed_run.error_code = type(exc).__name__[:100]
                failed_run.error_detail = str(exc)[:4000]
                failed_run.completed_at = datetime.now(UTC)

    try:
        model = GeminiComparisonModel(settings)
    except Exception as exc:
        await record_failure(exc)
        raise

    async def summary_generator(context: dict[str, object]) -> Any:
        async with tenant_transaction(organization_id) as evaluation_session:
            current = await evaluation_session.scalar(
                select(Evaluation).where(
                    Evaluation.organization_id == organization_id,
                    Evaluation.id == evaluation_id,
                )
            )
            if current is None or current.content_digest != source_digest:
                raise ValueError("Evaluation source became stale during generation")
            provider_context = dict(context)
            provider_context["deterministic_evaluation"] = current.snapshot
        invocation_id = uuid.uuid5(graph_run_id, PROMPT_VERSION)
        async with tenant_transaction(organization_id) as invocation_session:
            invocation = await invocation_session.get(ModelInvocation, invocation_id)
            if invocation is None:
                invocation = ModelInvocation(
                    id=invocation_id,
                    organization_id=organization_id,
                    analysis_run_id=graph_run_id,
                    node_name="draft_grounded_summary",
                    provider="gemini",
                    model=settings.llm_model,
                    prompt_version=PROMPT_VERSION,
                    status=InvocationStatus.STARTED,
                    input_tokens=0,
                    output_tokens=0,
                    cost_amount=Decimal("0"),
                    cost_currency="USD",
                )
                invocation_session.add(invocation)
            else:
                invocation.status = InvocationStatus.STARTED
                invocation.error_code = None
        try:
            return await model.generate(provider_context)
        except Exception as exc:
            async with tenant_transaction(organization_id) as invocation_session:
                invocation = await invocation_session.get(ModelInvocation, invocation_id)
                if invocation is not None:
                    invocation.status = InvocationStatus.FAILED
                    invocation.error_code = type(exc).__name__[:100]
            raise

    config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_ns": f"organization:{organization_id}",
        }
    }
    try:
        async with AsyncPostgresSaver.from_conn_string(
            settings.effective_langgraph_database_url
        ) as checkpointer:
            await checkpointer.setup()
            graph = build_evaluation_analysis_graph(
                evidence_loader, summary_generator, checkpointer
            )
            if resume_payload is None:
                result = await graph.ainvoke(
                    {
                        "organization_id": str(organization_id),
                        "evaluation_id": str(evaluation_id),
                        "analysis_run_id": str(graph_run_id),
                        "source_digest": source_digest,
                        "submission_ids": submission_ids,
                        "unresolved_finding_ids": [str(value) for value in unresolved],
                        "status": "running",
                    },
                    config,
                )
            else:
                result = await graph.ainvoke(Command(resume=resume_payload), config)

        interrupted = bool(result.get("__interrupt__"))
        output: dict[str, object] = {
            "comparison_summary": result.get("comparison_summary", {}),
            "authorized_evidence_ids": result.get("authorized_evidence_ids", []),
            "citations_validated": bool(result.get("citations_validated")),
        }
        async with tenant_transaction(organization_id) as session:
            job = await session.scalar(
                select(Job)
                .where(Job.organization_id == organization_id, Job.id == job_id)
                .with_for_update()
            )
            run = await session.scalar(
                select(AnalysisRun)
                .where(
                    AnalysisRun.organization_id == organization_id,
                    AnalysisRun.id == graph_run_id,
                )
                .with_for_update()
            )
            if job is None or run is None:
                raise ValueError("Analysis job disappeared during execution")
            invocation_data = cast(dict[str, object], result.get("model_invocation", {}))
            if invocation_data:
                invocation_id = uuid.uuid5(graph_run_id, str(invocation_data["prompt_version"]))
                invocation = await session.get(ModelInvocation, invocation_id)
                if invocation is None:
                    invocation = ModelInvocation(
                        id=invocation_id,
                        organization_id=organization_id,
                        analysis_run_id=graph_run_id,
                        node_name="draft_grounded_summary",
                        provider=str(invocation_data["provider"]),
                        model=str(invocation_data["model"]),
                        prompt_version=str(invocation_data["prompt_version"]),
                        status=InvocationStatus.COMPLETED,
                        input_tokens=cast(int, invocation_data["input_tokens"]),
                        output_tokens=cast(int, invocation_data["output_tokens"]),
                        cost_amount=Decimal("0"),
                        cost_currency="USD",
                        latency_ms=cast(int, invocation_data["latency_ms"]),
                        provider_request_id=cast(
                            str | None, invocation_data["provider_request_id"]
                        ),
                    )
                    session.add(invocation)
                else:
                    invocation.provider = str(invocation_data["provider"])
                    invocation.model = str(invocation_data["model"])
                    invocation.status = InvocationStatus.COMPLETED
                    invocation.input_tokens = cast(int, invocation_data["input_tokens"])
                    invocation.output_tokens = cast(int, invocation_data["output_tokens"])
                    invocation.latency_ms = cast(int, invocation_data["latency_ms"])
                    invocation.provider_request_id = cast(
                        str | None, invocation_data["provider_request_id"]
                    )
                    invocation.error_code = None
            run.output = output
            run.status = (
                AnalysisRunStatus.AWAITING_REVIEW if interrupted else AnalysisRunStatus.COMPLETED
            )
            if not interrupted:
                run.completed_at = datetime.now(UTC)
            job.status = JobStatus.COMPLETED
            job.result = {"analysis_run_id": str(run.id), "status": run.status.value}
            job.completed_at = datetime.now(UTC)
        return {"analysis_run_id": str(graph_run_id), "status": run.status.value}
    except Exception as exc:
        await record_failure(exc)
        raise


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="procurex.evaluation_analysis",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def run_evaluation_analysis(_: Any, organization_id: str, job_id: str) -> dict[str, object]:
    async def execute_and_close() -> dict[str, object]:
        try:
            return await _execute(uuid.UUID(organization_id), uuid.UUID(job_id))
        finally:
            await close_database()

    return asyncio.run(execute_and_close())
