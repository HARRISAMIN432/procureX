from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.context import RequestContext, require_permission
from app.models.awards import AwardDecisionValue
from app.schemas.awards import (
    AllocationScenarioCreate,
    AllocationScenarioList,
    AllocationScenarioRead,
    AwardCreate,
    AwardDecisionWrite,
    AwardRead,
    AwardSubmit,
)
from app.services.awards import (
    AwardConflictError,
    AwardNotFoundError,
    AwardValidationError,
    create_allocation_scenario,
    create_award,
    decide_award,
    list_allocation_scenarios,
    read_award,
    submit_award,
)

router = APIRouter(tags=["allocation and awards"])


async def execute[ResultT](command: Callable[[], Awaitable[ResultT]]) -> ResultT:
    try:
        return await command()
    except AwardNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "award_not_found", "message": str(exc)}
        ) from exc
    except AwardConflictError as exc:
        raise HTTPException(
            status_code=409, detail={"code": "award_conflict", "message": str(exc)}
        ) from exc
    except AwardValidationError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "award_validation_failed", "message": str(exc)}
        ) from exc


@router.post(
    "/evaluations/{evaluation_id}/allocation-scenarios",
    response_model=AllocationScenarioRead,
    status_code=status.HTTP_201_CREATED,
)
async def run_scenario(
    evaluation_id: UUID,
    payload: AllocationScenarioCreate,
    context: Annotated[RequestContext, Depends(require_permission("allocations.run"))],
) -> AllocationScenarioRead:
    return await execute(lambda: create_allocation_scenario(context, evaluation_id, payload))


@router.get(
    "/evaluations/{evaluation_id}/allocation-scenarios", response_model=AllocationScenarioList
)
async def list_scenarios(
    evaluation_id: UUID,
    context: Annotated[RequestContext, Depends(require_permission("evaluations.read"))],
) -> AllocationScenarioList:
    return await list_allocation_scenarios(context, evaluation_id)


@router.post(
    "/allocation-scenarios/{scenario_id}/awards",
    response_model=AwardRead,
    status_code=status.HTTP_201_CREATED,
)
async def prepare_award(
    scenario_id: UUID,
    payload: AwardCreate,
    context: Annotated[RequestContext, Depends(require_permission("awards.write"))],
) -> AwardRead:
    return await execute(lambda: create_award(context, scenario_id, payload))


@router.get("/awards/{award_id}", response_model=AwardRead)
async def get_award(
    award_id: UUID, context: Annotated[RequestContext, Depends(require_permission("awards.read"))]
) -> AwardRead:
    return await execute(lambda: read_award(context, award_id))


@router.post("/awards/{award_id}/submit", response_model=AwardRead)
async def submit(
    award_id: UUID,
    payload: AwardSubmit,
    context: Annotated[RequestContext, Depends(require_permission("awards.write"))],
) -> AwardRead:
    return await execute(lambda: submit_award(context, award_id, payload))


@router.post("/awards/{award_id}/approve", response_model=AwardRead)
async def approve(
    award_id: UUID,
    payload: AwardDecisionWrite,
    context: Annotated[RequestContext, Depends(require_permission("awards.approve"))],
) -> AwardRead:
    return await execute(
        lambda: decide_award(context, award_id, AwardDecisionValue.APPROVE, payload)
    )


@router.post("/awards/{award_id}/reject", response_model=AwardRead)
async def reject(
    award_id: UUID,
    payload: AwardDecisionWrite,
    context: Annotated[RequestContext, Depends(require_permission("awards.approve"))],
) -> AwardRead:
    return await execute(
        lambda: decide_award(context, award_id, AwardDecisionValue.REJECT, payload)
    )
