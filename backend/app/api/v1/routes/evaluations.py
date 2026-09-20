from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.auth.context import RequestContext, require_permission
from app.schemas.evaluations import (
    AnalysisResume,
    AnalysisRunRead,
    EvaluationCreate,
    EvaluationRead,
)
from app.services.evaluation_analysis import (
    create_analysis_run,
    read_analysis_run,
    resume_analysis_run,
)
from app.services.evaluations import (
    EvaluationConflictError,
    EvaluationNotFoundError,
    EvaluationValidationError,
    create_evaluation,
    read_evaluation,
)
from app.workers.evaluations import enqueue_evaluation_analysis

router = APIRouter(tags=["evaluations"])


async def execute[ResultT](command: Callable[[], Awaitable[ResultT]]) -> ResultT:
    try:
        return await command()
    except EvaluationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "evaluation_not_found", "message": str(exc)},
        ) from exc
    except EvaluationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "evaluation_conflict", "message": str(exc)},
        ) from exc
    except EvaluationValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "evaluation_validation_failed", "message": str(exc)},
        ) from exc


@router.post(
    "/rfqs/{rfq_id}/evaluations",
    response_model=EvaluationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create(
    rfq_id: UUID,
    payload: EvaluationCreate,
    context: Annotated[RequestContext, Depends(require_permission("evaluations.run"))],
) -> EvaluationRead:
    return await execute(lambda: create_evaluation(context, rfq_id, payload))


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationRead)
async def get_one(
    evaluation_id: UUID,
    context: Annotated[RequestContext, Depends(require_permission("evaluations.read"))],
) -> EvaluationRead:
    return await execute(lambda: read_evaluation(context, evaluation_id))


@router.post(
    "/evaluations/{evaluation_id}/analysis-runs",
    response_model=AnalysisRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_analysis(
    evaluation_id: UUID,
    background_tasks: BackgroundTasks,
    context: Annotated[RequestContext, Depends(require_permission("evaluations.run"))],
) -> AnalysisRunRead:
    run, job_id = await execute(lambda: create_analysis_run(context, evaluation_id))
    if job_id is not None:
        background_tasks.add_task(enqueue_evaluation_analysis, context.organization_id, job_id)
    return run


@router.get("/evaluation-analysis-runs/{analysis_run_id}", response_model=AnalysisRunRead)
async def get_analysis(
    analysis_run_id: UUID,
    context: Annotated[RequestContext, Depends(require_permission("evaluations.read"))],
) -> AnalysisRunRead:
    return await execute(lambda: read_analysis_run(context, analysis_run_id))


@router.post(
    "/evaluation-analysis-runs/{analysis_run_id}/resume",
    response_model=AnalysisRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_analysis(
    analysis_run_id: UUID,
    payload: AnalysisResume,
    background_tasks: BackgroundTasks,
    context: Annotated[RequestContext, Depends(require_permission("evaluations.run"))],
) -> AnalysisRunRead:
    run, job_id = await execute(lambda: resume_analysis_run(context, analysis_run_id, payload))
    background_tasks.add_task(enqueue_evaluation_analysis, context.organization_id, job_id)
    return run
