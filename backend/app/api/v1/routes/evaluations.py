from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.context import RequestContext, require_permission
from app.schemas.evaluations import EvaluationCreate, EvaluationRead
from app.services.evaluations import (
    EvaluationConflictError,
    EvaluationNotFoundError,
    EvaluationValidationError,
    create_evaluation,
    read_evaluation,
)

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
