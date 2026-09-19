from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.context import RequestContext, require_permission
from app.schemas.requisitions import (
    RequisitionCancel,
    RequisitionCreate,
    RequisitionList,
    RequisitionRead,
    RequisitionReplace,
    RequisitionTransition,
)
from app.services.requisitions import (
    RequisitionNotFoundError,
    RequisitionStateError,
    RequisitionValidationError,
    RequisitionVersionConflictError,
    cancel_requisition,
    create_requisition,
    list_requisitions,
    read_requisition,
    replace_requisition,
    submit_requisition,
)

router = APIRouter(prefix="/requisitions", tags=["requisitions"])


async def execute[ResultT](command: Callable[[], Awaitable[ResultT]]) -> ResultT:
    try:
        return await command()
    except RequisitionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "requisition_not_found", "message": str(exc)},
        ) from exc
    except RequisitionVersionConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "version_conflict", "message": str(exc)},
        ) from exc
    except RequisitionStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "invalid_requisition_state", "message": str(exc)},
        ) from exc
    except RequisitionValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "requisition_not_submittable", "message": str(exc)},
        ) from exc


@router.post("", response_model=RequisitionRead, status_code=status.HTTP_201_CREATED)
async def create(
    payload: RequisitionCreate,
    context: Annotated[RequestContext, Depends(require_permission("requisitions.write"))],
) -> RequisitionRead:
    return await execute(lambda: create_requisition(context, payload))


@router.get("", response_model=RequisitionList)
async def list_all(
    context: Annotated[RequestContext, Depends(require_permission("requisitions.read"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RequisitionList:
    return await list_requisitions(context, limit, offset)


@router.get("/{requisition_id}", response_model=RequisitionRead)
async def get_one(
    requisition_id: UUID,
    context: Annotated[RequestContext, Depends(require_permission("requisitions.read"))],
) -> RequisitionRead:
    return await execute(lambda: read_requisition(context, requisition_id))


@router.put("/{requisition_id}", response_model=RequisitionRead)
async def replace(
    requisition_id: UUID,
    payload: RequisitionReplace,
    context: Annotated[RequestContext, Depends(require_permission("requisitions.write"))],
) -> RequisitionRead:
    return await execute(lambda: replace_requisition(context, requisition_id, payload))


@router.post("/{requisition_id}/submit", response_model=RequisitionRead)
async def submit(
    requisition_id: UUID,
    payload: RequisitionTransition,
    context: Annotated[RequestContext, Depends(require_permission("requisitions.submit"))],
) -> RequisitionRead:
    return await execute(lambda: submit_requisition(context, requisition_id, payload))


@router.post("/{requisition_id}/cancel", response_model=RequisitionRead)
async def cancel(
    requisition_id: UUID,
    payload: RequisitionCancel,
    context: Annotated[RequestContext, Depends(require_permission("requisitions.cancel"))],
) -> RequisitionRead:
    return await execute(lambda: cancel_requisition(context, requisition_id, payload))
