from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.context import RequestContext, require_permission
from app.schemas.suppliers import (
    CertificateCreate,
    CertificateReview,
    QualificationCreate,
    QualificationDecision,
    SupplierCreate,
    SupplierList,
    SupplierRead,
    SupplierReplace,
    SupplierStatusChange,
)
from app.services.suppliers import (
    SupplierConflictError,
    SupplierNotFoundError,
    SupplierValidationError,
    approve_supplier,
    create_certificate,
    create_qualification,
    create_supplier,
    decide_qualification,
    list_suppliers,
    read_supplier,
    replace_supplier,
    review_certificate,
    suspend_supplier,
)

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


async def execute[ResultT](command: Callable[[], Awaitable[ResultT]]) -> ResultT:
    try:
        return await command()
    except SupplierNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "supplier_not_found", "message": str(exc)},
        ) from exc
    except SupplierConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "supplier_conflict", "message": str(exc)},
        ) from exc
    except SupplierValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "supplier_validation_failed", "message": str(exc)},
        ) from exc


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
async def create(
    payload: SupplierCreate,
    context: Annotated[RequestContext, Depends(require_permission("suppliers.write"))],
) -> SupplierRead:
    return await execute(lambda: create_supplier(context, payload))


@router.get("", response_model=SupplierList)
async def list_all(
    context: Annotated[RequestContext, Depends(require_permission("suppliers.read"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SupplierList:
    return await list_suppliers(context, limit, offset)


@router.get("/{supplier_id}", response_model=SupplierRead)
async def get_one(
    supplier_id: UUID,
    context: Annotated[RequestContext, Depends(require_permission("suppliers.read"))],
) -> SupplierRead:
    return await execute(lambda: read_supplier(context, supplier_id))


@router.put("/{supplier_id}", response_model=SupplierRead)
async def replace(
    supplier_id: UUID,
    payload: SupplierReplace,
    context: Annotated[RequestContext, Depends(require_permission("suppliers.write"))],
) -> SupplierRead:
    return await execute(lambda: replace_supplier(context, supplier_id, payload))


@router.post("/{supplier_id}/qualifications", response_model=SupplierRead)
async def add_qualification(
    supplier_id: UUID,
    payload: QualificationCreate,
    context: Annotated[RequestContext, Depends(require_permission("suppliers.qualify"))],
) -> SupplierRead:
    return await execute(lambda: create_qualification(context, supplier_id, payload))


@router.post(
    "/{supplier_id}/qualifications/{qualification_id}/decision",
    response_model=SupplierRead,
)
async def qualification_decision(
    supplier_id: UUID,
    qualification_id: UUID,
    payload: QualificationDecision,
    context: Annotated[RequestContext, Depends(require_permission("suppliers.qualify"))],
) -> SupplierRead:
    return await execute(
        lambda: decide_qualification(context, supplier_id, qualification_id, payload)
    )


@router.post("/{supplier_id}/certificates", response_model=SupplierRead)
async def add_certificate(
    supplier_id: UUID,
    payload: CertificateCreate,
    context: Annotated[RequestContext, Depends(require_permission("suppliers.qualify"))],
) -> SupplierRead:
    return await execute(lambda: create_certificate(context, supplier_id, payload))


@router.post(
    "/{supplier_id}/certificates/{certificate_id}/review",
    response_model=SupplierRead,
)
async def certificate_review(
    supplier_id: UUID,
    certificate_id: UUID,
    payload: CertificateReview,
    context: Annotated[RequestContext, Depends(require_permission("suppliers.qualify"))],
) -> SupplierRead:
    return await execute(lambda: review_certificate(context, supplier_id, certificate_id, payload))


@router.post("/{supplier_id}/approve", response_model=SupplierRead)
async def approve(
    supplier_id: UUID,
    payload: SupplierStatusChange,
    context: Annotated[RequestContext, Depends(require_permission("suppliers.approve"))],
) -> SupplierRead:
    return await execute(lambda: approve_supplier(context, supplier_id, payload))


@router.post("/{supplier_id}/suspend", response_model=SupplierRead)
async def suspend(
    supplier_id: UUID,
    payload: SupplierStatusChange,
    context: Annotated[RequestContext, Depends(require_permission("suppliers.approve"))],
) -> SupplierRead:
    return await execute(lambda: suspend_supplier(context, supplier_id, payload))
