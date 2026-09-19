from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.context import RequestContext, require_permission
from app.models.approvals import ApprovalDecisionValue
from app.schemas.approvals import (
    ApprovalDecisionWrite,
    ApprovalPolicyCreate,
    ApprovalPolicyRead,
    ApprovalRequestCreate,
    ApprovalRequestRead,
    BudgetCreate,
    BudgetList,
    BudgetRead,
)
from app.services.approvals import (
    ControlConflictError,
    ControlNotFoundError,
    ControlValidationError,
    create_approval_policy,
    create_budget,
    decide_approval,
    list_budgets,
    read_approval_request,
    request_requisition_approval,
)

router = APIRouter(tags=["approvals and budgets"])


async def execute[ResultT](command: Callable[[], Awaitable[ResultT]]) -> ResultT:
    try:
        return await command()
    except ControlNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "control_not_found", "message": str(exc)},
        ) from exc
    except ControlConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "control_conflict", "message": str(exc)},
        ) from exc
    except ControlValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "control_validation_failed", "message": str(exc)},
        ) from exc


@router.post("/budgets", response_model=BudgetRead, status_code=status.HTTP_201_CREATED)
async def create_budget_endpoint(
    payload: BudgetCreate,
    context: Annotated[RequestContext, Depends(require_permission("budgets.manage"))],
) -> BudgetRead:
    return await execute(lambda: create_budget(context, payload))


@router.get("/budgets", response_model=BudgetList)
async def list_budgets_endpoint(
    context: Annotated[RequestContext, Depends(require_permission("budgets.read"))],
) -> BudgetList:
    return await list_budgets(context)


@router.post(
    "/approval-policies",
    response_model=ApprovalPolicyRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_policy_endpoint(
    payload: ApprovalPolicyCreate,
    context: Annotated[RequestContext, Depends(require_permission("approvals.policies.manage"))],
) -> ApprovalPolicyRead:
    return await execute(lambda: create_approval_policy(context, payload))


@router.post(
    "/requisitions/{requisition_id}/approval-requests",
    response_model=ApprovalRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def request_approval_endpoint(
    requisition_id: UUID,
    payload: ApprovalRequestCreate,
    context: Annotated[RequestContext, Depends(require_permission("approvals.request"))],
) -> ApprovalRequestRead:
    return await execute(lambda: request_requisition_approval(context, requisition_id, payload))


@router.get("/approval-requests/{approval_request_id}", response_model=ApprovalRequestRead)
async def read_approval_endpoint(
    approval_request_id: UUID,
    context: Annotated[RequestContext, Depends(require_permission("approvals.read"))],
) -> ApprovalRequestRead:
    return await execute(lambda: read_approval_request(context, approval_request_id))


@router.post("/approval-requests/{approval_request_id}/approve", response_model=ApprovalRequestRead)
async def approve_endpoint(
    approval_request_id: UUID,
    payload: ApprovalDecisionWrite,
    context: Annotated[RequestContext, Depends(require_permission("approvals.decide"))],
) -> ApprovalRequestRead:
    if "budgets.reserve" not in context.permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "permission_denied", "message": "budgets.reserve is required"},
        )
    return await execute(
        lambda: decide_approval(
            context, approval_request_id, ApprovalDecisionValue.APPROVE, payload
        )
    )


@router.post("/approval-requests/{approval_request_id}/reject", response_model=ApprovalRequestRead)
async def reject_endpoint(
    approval_request_id: UUID,
    payload: ApprovalDecisionWrite,
    context: Annotated[RequestContext, Depends(require_permission("approvals.decide"))],
) -> ApprovalRequestRead:
    return await execute(
        lambda: decide_approval(context, approval_request_id, ApprovalDecisionValue.REJECT, payload)
    )
