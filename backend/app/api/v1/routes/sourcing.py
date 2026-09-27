from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from app.auth.context import RequestContext, require_permission
from app.schemas.sourcing import (
    ClarificationAnswer,
    ClarificationCreate,
    ClarificationRead,
    InvitationCreate,
    InvitationRead,
    RfqAmend,
    RfqCancel,
    RfqCreate,
    RfqList,
    RfqRead,
    RfqReplace,
    RfqTransition,
)
from app.services.sourcing import (
    SourcingConflictError,
    SourcingNotFoundError,
    SourcingValidationError,
    amend_rfq,
    answer_clarification,
    cancel_rfq,
    close_rfq,
    create_clarification,
    create_rfq,
    invite_suppliers,
    list_rfqs,
    publish_rfq,
    queue_supplier_invitation_email,
    read_rfq,
    replace_rfq,
)
from app.workers.supplier_notifications import enqueue_supplier_invitation_email

router = APIRouter(tags=["sourcing"])


async def execute[ResultT](command: Callable[[], Awaitable[ResultT]]) -> ResultT:
    try:
        return await command()
    except SourcingNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "sourcing_not_found", "message": str(exc)},
        ) from exc
    except SourcingConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "sourcing_conflict", "message": str(exc)},
        ) from exc
    except SourcingValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "sourcing_validation_failed", "message": str(exc)},
        ) from exc


@router.post("/rfqs", response_model=RfqRead, status_code=status.HTTP_201_CREATED)
async def create(
    payload: RfqCreate,
    context: Annotated[RequestContext, Depends(require_permission("sourcing.write"))],
) -> RfqRead:
    return await execute(lambda: create_rfq(context, payload))


@router.get("/rfqs", response_model=RfqList)
async def list_all(
    context: Annotated[RequestContext, Depends(require_permission("sourcing.read"))],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RfqList:
    return await list_rfqs(context, limit, offset)


@router.get("/rfqs/{rfq_id}", response_model=RfqRead)
async def get_one(
    rfq_id: UUID,
    context: Annotated[RequestContext, Depends(require_permission("sourcing.read"))],
) -> RfqRead:
    return await execute(lambda: read_rfq(context, rfq_id))


@router.put("/rfqs/{rfq_id}", response_model=RfqRead)
async def replace(
    rfq_id: UUID,
    payload: RfqReplace,
    context: Annotated[RequestContext, Depends(require_permission("sourcing.write"))],
) -> RfqRead:
    return await execute(lambda: replace_rfq(context, rfq_id, payload))


@router.post("/rfqs/{rfq_id}/invitations", response_model=RfqRead)
async def invite(
    rfq_id: UUID,
    payload: InvitationCreate,
    context: Annotated[RequestContext, Depends(require_permission("sourcing.invite"))],
) -> RfqRead:
    return await execute(lambda: invite_suppliers(context, rfq_id, payload))


@router.post("/rfqs/{rfq_id}/publish", response_model=RfqRead)
async def publish(
    rfq_id: UUID,
    payload: RfqTransition,
    context: Annotated[RequestContext, Depends(require_permission("sourcing.publish"))],
    background_tasks: BackgroundTasks,
) -> RfqRead:
    rfq = await execute(lambda: publish_rfq(context, rfq_id, payload))
    for invitation in rfq.invitations:
        background_tasks.add_task(
            enqueue_supplier_invitation_email,
            context.organization_id,
            invitation.id,
            rfq.publication_number,
        )
    return rfq


@router.post("/rfqs/{rfq_id}/amend", response_model=RfqRead)
async def amend(
    rfq_id: UUID,
    payload: RfqAmend,
    context: Annotated[RequestContext, Depends(require_permission("sourcing.publish"))],
    background_tasks: BackgroundTasks,
) -> RfqRead:
    rfq = await execute(lambda: amend_rfq(context, rfq_id, payload))
    for invitation in rfq.invitations:
        if invitation.status.value != "revoked":
            background_tasks.add_task(
                enqueue_supplier_invitation_email,
                context.organization_id,
                invitation.id,
                rfq.publication_number,
            )
    return rfq


@router.post("/rfq-invitations/{invitation_id}/send-email", response_model=InvitationRead)
async def resend_supplier_invitation(
    invitation_id: UUID,
    context: Annotated[RequestContext, Depends(require_permission("sourcing.invite"))],
    background_tasks: BackgroundTasks,
) -> InvitationRead:
    invitation = await execute(lambda: queue_supplier_invitation_email(context, invitation_id))
    background_tasks.add_task(
        enqueue_supplier_invitation_email,
        context.organization_id,
        invitation.id,
        invitation.email_publication_number,
    )
    return invitation


@router.post("/rfqs/{rfq_id}/close", response_model=RfqRead)
async def close(
    rfq_id: UUID,
    payload: RfqTransition,
    context: Annotated[RequestContext, Depends(require_permission("sourcing.publish"))],
) -> RfqRead:
    return await execute(lambda: close_rfq(context, rfq_id, payload))


@router.post("/rfqs/{rfq_id}/cancel", response_model=RfqRead)
async def cancel(
    rfq_id: UUID,
    payload: RfqCancel,
    context: Annotated[RequestContext, Depends(require_permission("sourcing.publish"))],
) -> RfqRead:
    return await execute(lambda: cancel_rfq(context, rfq_id, payload))


@router.post(
    "/rfqs/{rfq_id}/clarifications",
    response_model=ClarificationRead,
    status_code=status.HTTP_201_CREATED,
)
async def ask(
    rfq_id: UUID,
    payload: ClarificationCreate,
    context: Annotated[
        RequestContext, Depends(require_permission("sourcing.clarifications.write"))
    ],
) -> ClarificationRead:
    return await execute(lambda: create_clarification(context, rfq_id, payload))


@router.post(
    "/rfqs/{rfq_id}/clarifications/{clarification_id}/answer",
    response_model=ClarificationRead,
)
async def answer(
    rfq_id: UUID,
    clarification_id: UUID,
    payload: ClarificationAnswer,
    context: Annotated[
        RequestContext, Depends(require_permission("sourcing.clarifications.write"))
    ],
) -> ClarificationRead:
    return await execute(lambda: answer_clarification(context, rfq_id, clarification_id, payload))
