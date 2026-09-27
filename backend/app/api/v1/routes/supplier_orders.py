"""Supplier acknowledgement for an issued purchase order."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.v1.routes.operations import execute
from app.auth.supplier import SupplierOrderContext, get_supplier_order_context
from app.models.operations import PurchaseOrderStatus
from app.schemas.operations import PurchaseOrderAcknowledge, PurchaseOrderLineRead
from app.services.operations import acknowledge_purchase_order, read_purchase_order

router = APIRouter(
    prefix="/supplier/orders/{organization_id}/{purchase_order_id}", tags=["supplier portal"]
)
Principal = Annotated[SupplierOrderContext, Depends(get_supplier_order_context)]


class SupplierOrderView(BaseModel):
    id: UUID
    po_number: str
    status: str
    version: int
    current_revision: int
    currency: str
    total_amount: str
    content_digest: str
    lines: list[PurchaseOrderLineRead]


async def _view(context: SupplierOrderContext) -> SupplierOrderView:
    order = await read_purchase_order(context.operation_context(), context.purchase_order_id)
    if order.supplier_id != context.supplier_id or order.status in {
        PurchaseOrderStatus.DRAFT,
        PurchaseOrderStatus.PENDING_AUTHORIZATION,
        PurchaseOrderStatus.AUTHORIZED,
    }:
        raise HTTPException(status_code=404, detail="Order not available")
    return SupplierOrderView(
        id=order.id,
        po_number=order.po_number,
        status=order.status.value,
        version=order.version,
        current_revision=order.current_revision,
        currency=order.currency,
        total_amount=str(order.total_amount),
        content_digest=order.content_digest,
        lines=order.current.lines,
    )


@router.get("", response_model=SupplierOrderView)
async def get_order(context: Principal) -> SupplierOrderView:
    return await _view(context)


@router.post("/acknowledge", response_model=SupplierOrderView)
async def acknowledge(payload: PurchaseOrderAcknowledge, context: Principal) -> SupplierOrderView:
    await _view(context)
    await execute(
        lambda: acknowledge_purchase_order(
            context.operation_context(), context.purchase_order_id, payload
        )
    )
    return await _view(context)
