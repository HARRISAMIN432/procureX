import uuid

from sqlalchemy import select

from app.auth.context import RequestContext
from app.models.ai import AnalysisRun, AnalysisRunStatus
from app.models.evaluations import Evaluation
from app.models.platform import ActorType, AuditEvent, Job, JobStatus, OutboxEvent
from app.schemas.evaluations import AnalysisResume, AnalysisRunRead
from app.services.evaluations import EvaluationConflictError, EvaluationNotFoundError

GRAPH_NAME = "evaluation_graph"
GRAPH_VERSION = "2.0.0"


def _read(run: AnalysisRun) -> AnalysisRunRead:
    if run.evaluation_id is None:
        raise ValueError("Evaluation analysis run is missing evaluation_id")
    return AnalysisRunRead(
        id=run.id,
        evaluation_id=run.evaluation_id,
        graph_name=run.graph_name,
        graph_version=run.graph_version,
        thread_id=run.thread_id,
        source_digest=run.source_digest,
        status=run.status,
        output=run.output,
        error_code=run.error_code,
        error_detail=run.error_detail,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


async def create_analysis_run(
    context: RequestContext, evaluation_id: uuid.UUID
) -> tuple[AnalysisRunRead, uuid.UUID | None]:
    evaluation = await context.session.scalar(
        select(Evaluation)
        .where(
            Evaluation.organization_id == context.organization_id,
            Evaluation.id == evaluation_id,
        )
        .with_for_update()
    )
    if evaluation is None:
        raise EvaluationNotFoundError("Evaluation not found")
    existing = await context.session.scalar(
        select(AnalysisRun)
        .where(
            AnalysisRun.organization_id == context.organization_id,
            AnalysisRun.evaluation_id == evaluation.id,
            AnalysisRun.source_digest == evaluation.content_digest,
            AnalysisRun.graph_name == GRAPH_NAME,
            AnalysisRun.status.in_(
                [
                    AnalysisRunStatus.QUEUED,
                    AnalysisRunStatus.RUNNING,
                    AnalysisRunStatus.AWAITING_REVIEW,
                    AnalysisRunStatus.COMPLETED,
                ]
            ),
        )
        .order_by(AnalysisRun.created_at.desc())
    )
    if existing is not None:
        pending_job_id = None
        if existing.status is AnalysisRunStatus.QUEUED:
            pending_job_id = await context.session.scalar(
                select(Job.id).where(
                    Job.organization_id == context.organization_id,
                    Job.correlation_id == str(existing.id),
                    Job.status.in_([JobStatus.QUEUED, JobStatus.RETRY_SCHEDULED]),
                )
            )
        return _read(existing), pending_job_id

    run_id = uuid.uuid4()
    thread_id = f"org:{context.organization_id}:evaluation:{evaluation.id}:run:{run_id}"
    run = AnalysisRun(
        id=run_id,
        organization_id=context.organization_id,
        graph_name=GRAPH_NAME,
        graph_version=GRAPH_VERSION,
        thread_id=thread_id,
        evaluation_id=evaluation.id,
        source_digest=evaluation.content_digest,
        status=AnalysisRunStatus.QUEUED,
        input={"evaluation_id": str(evaluation.id)},
        created_by_user_id=context.user_id,
    )
    job = Job(
        id=uuid.uuid4(),
        organization_id=context.organization_id,
        job_type="evaluation.analysis",
        idempotency_key=f"evaluation.analysis:{evaluation.id}:{evaluation.content_digest}",
        payload={"analysis_run_id": str(run.id), "evaluation_id": str(evaluation.id)},
        correlation_id=str(run.id),
        max_attempts=3,
    )
    context.session.add_all(
        [
            run,
            job,
            AuditEvent(
                organization_id=context.organization_id,
                actor_type=ActorType.USER,
                actor_id=context.user_id,
                action="evaluation.analysis_queued",
                object_type="analysis_run",
                object_id=run.id,
                changes={"evaluation_id": str(evaluation.id)},
            ),
            OutboxEvent(
                organization_id=context.organization_id,
                aggregate_type="analysis_run",
                aggregate_id=run.id,
                aggregate_version=1,
                event_type="evaluation.analysis_queued",
                schema_version=1,
                payload={
                    "analysis_run_id": str(run.id),
                    "evaluation_id": str(evaluation.id),
                    "job_id": str(job.id),
                },
                actor_id=context.user_id,
            ),
        ]
    )
    await context.session.flush()
    return _read(run), job.id


async def read_analysis_run(context: RequestContext, analysis_run_id: uuid.UUID) -> AnalysisRunRead:
    run = await context.session.scalar(
        select(AnalysisRun).where(
            AnalysisRun.organization_id == context.organization_id,
            AnalysisRun.id == analysis_run_id,
            AnalysisRun.graph_name == GRAPH_NAME,
        )
    )
    if run is None:
        raise EvaluationNotFoundError("Evaluation analysis run not found")
    return _read(run)


async def resume_analysis_run(
    context: RequestContext,
    analysis_run_id: uuid.UUID,
    payload: AnalysisResume,
) -> tuple[AnalysisRunRead, uuid.UUID]:
    run = await context.session.scalar(
        select(AnalysisRun)
        .where(
            AnalysisRun.organization_id == context.organization_id,
            AnalysisRun.id == analysis_run_id,
            AnalysisRun.graph_name == GRAPH_NAME,
        )
        .with_for_update()
    )
    if run is None:
        raise EvaluationNotFoundError("Evaluation analysis run not found")
    if run.status is AnalysisRunStatus.QUEUED:
        existing_job_id = await context.session.scalar(
            select(Job.id).where(
                Job.organization_id == context.organization_id,
                Job.correlation_id == str(run.id),
                Job.job_type == "evaluation.analysis.resume",
                Job.status.in_([JobStatus.QUEUED, JobStatus.RETRY_SCHEDULED]),
            )
        )
        if existing_job_id is not None:
            return _read(run), existing_job_id
    if run.status is not AnalysisRunStatus.AWAITING_REVIEW:
        raise EvaluationConflictError("Only an awaiting-review analysis can be resumed")
    if payload.source_digest != run.source_digest:
        raise EvaluationConflictError("Analysis resume source digest is stale")
    run.status = AnalysisRunStatus.QUEUED
    job = Job(
        id=uuid.uuid4(),
        organization_id=context.organization_id,
        job_type="evaluation.analysis.resume",
        idempotency_key=f"evaluation.analysis.resume:{run.id}:{run.source_digest}",
        payload={
            "analysis_run_id": str(run.id),
            "evaluation_id": str(run.evaluation_id),
            "resume": {"review_complete": True, "source_digest": run.source_digest},
        },
        correlation_id=str(run.id),
        max_attempts=3,
        status=JobStatus.QUEUED,
    )
    context.session.add(job)
    await context.session.flush()
    return _read(run), job.id
