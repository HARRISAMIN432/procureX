from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.auth.context import RequestContext, require_permission
from app.models.commercial import AfterSalesCase, OrganizationClosureRequest, SupportCase
from app.models.identity import Organization, OrganizationStatus
from app.schemas.commercial import (
    AfterSalesCaseCreate,
    AfterSalesCaseRead,
    AfterSalesCaseUpdate,
    ClosureCreate,
    ClosureRead,
    CommercialOverview,
    ExportRead,
    SubscriptionRead,
    SupportCaseCreate,
    SupportCaseRead,
    SupportCaseUpdate,
)
from app.services.commercial import (
    CommercialConflictError,
    create_after_sales_case,
    create_support_case,
    export_organization,
    record_event,
    schedule_closure,
    subscription_for,
    usage,
)

router = APIRouter(prefix="/commercial", tags=["commercial"])


@router.get("/overview", response_model=CommercialOverview)
async def overview(
    context: Annotated[RequestContext, Depends(require_permission("commercial.read"))],
) -> CommercialOverview:
    subscription = await subscription_for(context)
    members, stored, cases = await usage(context)
    return CommercialOverview(
        subscription=SubscriptionRead.model_validate(subscription),
        active_members=members,
        stored_bytes=stored,
        open_support_cases=cases,
        seat_usage_percent=round(members / subscription.seat_limit * 100, 1),
        storage_usage_percent=round(stored / subscription.storage_limit_bytes * 100, 1),
    )


@router.get("/support-cases", response_model=list[SupportCaseRead])
async def support_cases(
    context: Annotated[RequestContext, Depends(require_permission("support.read"))],
) -> list[SupportCase]:
    return list(
        await context.session.scalars(
            select(SupportCase)
            .where(SupportCase.organization_id == context.organization_id)
            .order_by(SupportCase.created_at.desc())
        )
    )


@router.post("/support-cases", response_model=SupportCaseRead, status_code=status.HTTP_201_CREATED)
async def add_support_case(
    payload: SupportCaseCreate,
    context: Annotated[RequestContext, Depends(require_permission("support.write"))],
) -> SupportCase:
    return await create_support_case(context, payload)


@router.patch("/support-cases/{case_id}", response_model=SupportCaseRead)
async def change_support_case(
    case_id: UUID,
    payload: SupportCaseUpdate,
    context: Annotated[RequestContext, Depends(require_permission("support.manage"))],
) -> SupportCase:
    case = await context.session.scalar(
        select(SupportCase)
        .where(SupportCase.organization_id == context.organization_id, SupportCase.id == case_id)
        .with_for_update()
    )
    if case is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "support_case_not_found", "message": "Support case not found"},
        )
    case.status, case.resolution = payload.status, payload.resolution
    case.resolved_at = datetime.now(UTC) if payload.status in {"resolved", "closed"} else None
    record_event(context, "support.case_updated", "support_case", case.id, {"status": case.status})
    return case


@router.post("/data-export", response_model=ExportRead)
async def data_export(
    context: Annotated[RequestContext, Depends(require_permission("organization.data.export"))],
) -> ExportRead:
    return await export_organization(context)


@router.post("/closure", response_model=ClosureRead, status_code=status.HTTP_201_CREATED)
async def close_workspace(
    payload: ClosureCreate,
    context: Annotated[
        RequestContext, Depends(require_permission("organization.lifecycle.manage"))
    ],
) -> OrganizationClosureRequest:
    try:
        return await schedule_closure(context, payload)
    except CommercialConflictError as exc:
        raise HTTPException(
            status_code=409, detail={"code": "closure_conflict", "message": str(exc)}
        ) from exc


@router.post("/closure/{closure_id}/cancel", response_model=ClosureRead)
async def cancel_closure(
    closure_id: UUID,
    context: Annotated[
        RequestContext, Depends(require_permission("organization.lifecycle.manage"))
    ],
) -> OrganizationClosureRequest:
    closure = await context.session.scalar(
        select(OrganizationClosureRequest)
        .where(
            OrganizationClosureRequest.organization_id == context.organization_id,
            OrganizationClosureRequest.id == closure_id,
            OrganizationClosureRequest.status == "scheduled",
        )
        .with_for_update()
    )
    if closure is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "closure_not_found", "message": "Scheduled closure not found"},
        )
    closure.status, closure.cancelled_at = "cancelled", datetime.now(UTC)
    organization = await context.session.get(Organization, context.organization_id)
    assert organization is not None
    organization.status = OrganizationStatus.ACTIVE
    record_event(
        context,
        "organization.closure_cancelled",
        "organization",
        organization.id,
        {"closure_id": str(closure.id)},
    )
    return closure


@router.get("/after-sales", response_model=list[AfterSalesCaseRead])
async def after_sales_cases(
    context: Annotated[RequestContext, Depends(require_permission("operations.after_sales.read"))],
) -> list[AfterSalesCase]:
    return list(
        await context.session.scalars(
            select(AfterSalesCase)
            .where(AfterSalesCase.organization_id == context.organization_id)
            .order_by(AfterSalesCase.created_at.desc())
        )
    )


@router.post("/after-sales", response_model=AfterSalesCaseRead, status_code=status.HTTP_201_CREATED)
async def add_after_sales_case(
    payload: AfterSalesCaseCreate,
    context: Annotated[RequestContext, Depends(require_permission("operations.after_sales.write"))],
) -> AfterSalesCase:
    try:
        return await create_after_sales_case(context, payload)
    except CommercialConflictError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "purchase_order_not_found", "message": str(exc)}
        ) from exc


@router.patch("/after-sales/{case_id}", response_model=AfterSalesCaseRead)
async def change_after_sales_case(
    case_id: UUID,
    payload: AfterSalesCaseUpdate,
    context: Annotated[RequestContext, Depends(require_permission("operations.after_sales.write"))],
) -> AfterSalesCase:
    case = await context.session.scalar(
        select(AfterSalesCase)
        .where(
            AfterSalesCase.organization_id == context.organization_id, AfterSalesCase.id == case_id
        )
        .with_for_update()
    )
    if case is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "after_sales_case_not_found", "message": "After-sales case not found"},
        )
    case.status, case.resolution = payload.status, payload.resolution
    case.resolved_at = (
        datetime.now(UTC) if payload.status in {"resolved", "rejected", "closed"} else None
    )
    record_event(
        context,
        "operations.after_sales_case_updated",
        "after_sales_case",
        case.id,
        {"status": case.status},
    )
    return case
