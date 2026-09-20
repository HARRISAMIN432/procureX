from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.context import RequestContext, require_permission
from app.schemas.operations import (
    AccountingExportCreate,
    AccountingExportRead,
    AccountingExportRetry,
    AccountingReconcile,
    ExceptionResolve,
    InvoiceApprove,
    InvoiceCapture,
    InvoiceMatchCreate,
    InvoiceMatchRead,
    InvoiceRead,
    PurchaseOrderAcknowledge,
    PurchaseOrderAmend,
    PurchaseOrderCreate,
    PurchaseOrderRead,
    ReceiptCreate,
    ReceiptRead,
    ReturnCreate,
    ReturnRead,
    VersionCommand,
)
from app.services.operations import (
    OperationsConflictError,
    OperationsNotFoundError,
    OperationsValidationError,
    acknowledge_purchase_order,
    amend_purchase_order,
    approve_invoice_for_export,
    authorize_purchase_order_amendment,
    capture_invoice,
    create_purchase_order,
    create_receipt,
    create_return,
    export_invoice,
    issue_purchase_order,
    match_invoice,
    read_invoice,
    read_purchase_order,
    reconcile_accounting_export,
    resolve_match_exception,
    retry_accounting_export,
)

router = APIRouter(tags=["order operations"])


async def execute[ResultT](command: Callable[[], Awaitable[ResultT]]) -> ResultT:
    try:
        return await command()
    except OperationsNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "operations_not_found", "message": str(exc)}
        ) from exc
    except OperationsConflictError as exc:
        raise HTTPException(
            status_code=409, detail={"code": "operations_conflict", "message": str(exc)}
        ) from exc
    except OperationsValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "operations_validation_failed", "message": str(exc)},
        ) from exc


@router.post(
    "/awards/{award_id}/purchase-orders",
    response_model=PurchaseOrderRead,
    status_code=status.HTTP_201_CREATED,
)
async def prepare_purchase_order(
    award_id: UUID,
    payload: PurchaseOrderCreate,
    context: Annotated[RequestContext, Depends(require_permission("orders.write"))],
) -> PurchaseOrderRead:
    return await execute(lambda: create_purchase_order(context, award_id, payload))


@router.get("/purchase-orders/{purchase_order_id}", response_model=PurchaseOrderRead)
async def get_purchase_order(
    purchase_order_id: UUID,
    context: Annotated[RequestContext, Depends(require_permission("orders.read"))],
) -> PurchaseOrderRead:
    return await execute(lambda: read_purchase_order(context, purchase_order_id))


@router.post("/purchase-orders/{purchase_order_id}/amend", response_model=PurchaseOrderRead)
async def amend(
    purchase_order_id: UUID,
    payload: PurchaseOrderAmend,
    context: Annotated[RequestContext, Depends(require_permission("orders.write"))],
) -> PurchaseOrderRead:
    return await execute(lambda: amend_purchase_order(context, purchase_order_id, payload))


@router.post(
    "/purchase-orders/{purchase_order_id}/authorize-amendment",
    response_model=PurchaseOrderRead,
)
async def authorize_amendment(
    purchase_order_id: UUID,
    payload: VersionCommand,
    context: Annotated[RequestContext, Depends(require_permission("orders.approve"))],
) -> PurchaseOrderRead:
    return await execute(
        lambda: authorize_purchase_order_amendment(context, purchase_order_id, payload)
    )


@router.post("/purchase-orders/{purchase_order_id}/issue", response_model=PurchaseOrderRead)
async def issue(
    purchase_order_id: UUID,
    payload: VersionCommand,
    context: Annotated[RequestContext, Depends(require_permission("orders.issue"))],
) -> PurchaseOrderRead:
    return await execute(lambda: issue_purchase_order(context, purchase_order_id, payload))


@router.post("/purchase-orders/{purchase_order_id}/acknowledge", response_model=PurchaseOrderRead)
async def acknowledge(
    purchase_order_id: UUID,
    payload: PurchaseOrderAcknowledge,
    context: Annotated[RequestContext, Depends(require_permission("orders.acknowledge"))],
) -> PurchaseOrderRead:
    return await execute(lambda: acknowledge_purchase_order(context, purchase_order_id, payload))


@router.post(
    "/purchase-orders/{purchase_order_id}/receipts",
    response_model=ReceiptRead,
    status_code=status.HTTP_201_CREATED,
)
async def receive(
    purchase_order_id: UUID,
    payload: ReceiptCreate,
    context: Annotated[RequestContext, Depends(require_permission("orders.receive"))],
) -> ReceiptRead:
    return await execute(lambda: create_receipt(context, purchase_order_id, payload))


@router.post(
    "/receipt-lines/{receipt_line_id}/returns",
    response_model=ReturnRead,
    status_code=status.HTTP_201_CREATED,
)
async def return_goods(
    receipt_line_id: UUID,
    payload: ReturnCreate,
    context: Annotated[RequestContext, Depends(require_permission("orders.receive"))],
) -> ReturnRead:
    return await execute(lambda: create_return(context, receipt_line_id, payload))


@router.post(
    "/purchase-orders/{purchase_order_id}/invoices",
    response_model=InvoiceRead,
    status_code=status.HTTP_201_CREATED,
)
async def capture(
    purchase_order_id: UUID,
    payload: InvoiceCapture,
    context: Annotated[RequestContext, Depends(require_permission("invoices.write"))],
) -> InvoiceRead:
    return await execute(lambda: capture_invoice(context, purchase_order_id, payload))


@router.get("/invoices/{invoice_id}", response_model=InvoiceRead)
async def get_invoice(
    invoice_id: UUID,
    context: Annotated[RequestContext, Depends(require_permission("invoices.read"))],
) -> InvoiceRead:
    return await execute(lambda: read_invoice(context, invoice_id))


@router.post("/invoices/{invoice_id}/match", response_model=InvoiceMatchRead)
async def match(
    invoice_id: UUID,
    payload: InvoiceMatchCreate,
    context: Annotated[RequestContext, Depends(require_permission("invoices.match"))],
) -> InvoiceMatchRead:
    return await execute(lambda: match_invoice(context, invoice_id, payload))


@router.post("/match-exceptions/{exception_id}/resolve", response_model=InvoiceMatchRead)
async def resolve_exception(
    exception_id: UUID,
    payload: ExceptionResolve,
    context: Annotated[RequestContext, Depends(require_permission("invoices.match"))],
) -> InvoiceMatchRead:
    return await execute(lambda: resolve_match_exception(context, exception_id, payload))


@router.post("/invoices/{invoice_id}/approve-for-export", response_model=InvoiceRead)
async def approve_for_export(
    invoice_id: UUID,
    payload: InvoiceApprove,
    context: Annotated[RequestContext, Depends(require_permission("invoices.approve"))],
) -> InvoiceRead:
    return await execute(lambda: approve_invoice_for_export(context, invoice_id, payload))


@router.post(
    "/invoices/{invoice_id}/accounting-exports",
    response_model=AccountingExportRead,
    status_code=status.HTTP_201_CREATED,
)
async def accounting_export(
    invoice_id: UUID,
    payload: AccountingExportCreate,
    context: Annotated[RequestContext, Depends(require_permission("accounting.export"))],
) -> AccountingExportRead:
    return await execute(lambda: export_invoice(context, invoice_id, payload))


@router.post("/accounting-exports/{export_id}/retry", response_model=AccountingExportRead)
async def retry_export(
    export_id: UUID,
    payload: AccountingExportRetry,
    context: Annotated[RequestContext, Depends(require_permission("accounting.export"))],
) -> AccountingExportRead:
    return await execute(lambda: retry_accounting_export(context, export_id, payload))


@router.post("/accounting-exports/{export_id}/reconcile", response_model=AccountingExportRead)
async def reconcile_export(
    export_id: UUID,
    payload: AccountingReconcile,
    context: Annotated[RequestContext, Depends(require_permission("accounting.reconcile"))],
) -> AccountingExportRead:
    return await execute(lambda: reconcile_accounting_export(context, export_id, payload))
