"""Supplier-only invitation surface; never serializes the buyer RFQ view."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.v1.routes.documents import execute as execute_document
from app.api.v1.routes.sourcing import execute
from app.auth.supplier import SupplierContext, get_supplier_context
from app.core.config import Settings, get_settings
from app.models.documents import Document, DocumentVersion, DocumentVersionStatus
from app.models.sourcing import (
    ClarificationVisibility,
    QuoteSubmission,
    Rfq,
    RfqClarification,
    RfqInvitation,
    RfqItem,
    RfqRequirement,
    RfqStatus,
)
from app.schemas.documents import (
    DocumentDownloadRead,
    DocumentRead,
    DocumentUploadComplete,
    DocumentUploadIntentCreate,
    DocumentUploadIntentRead,
)
from app.schemas.sourcing import (
    ClarificationCreate,
    ClarificationRead,
    InvitationAcknowledge,
    InvitationNoBid,
    InvitationRead,
    RfqItemRead,
    RfqRequirementRead,
    SubmissionCreate,
    SubmissionRead,
    SubmissionWithdraw,
)
from app.services.documents import complete_upload, create_download_url, create_upload_intent
from app.services.sourcing import (
    acknowledge_invitation,
    create_clarification,
    decline_invitation,
    read_submission,
    submit_quote,
    withdraw_quote,
)
from app.workers.documents import enqueue_document_scan

router = APIRouter(
    prefix="/supplier/invitations/{organization_id}/{invitation_id}", tags=["supplier portal"]
)
Principal = Annotated[SupplierContext, Depends(get_supplier_context)]


class SupplierInvitationView(BaseModel):
    organization_id: UUID
    invitation: InvitationRead
    rfq_id: UUID
    title: str
    currency: str
    submission_deadline: str
    status: str
    version: int
    publication_number: int
    terms: dict[str, object]
    items: list[RfqItemRead]
    requirements: list[RfqRequirementRead]
    submissions: list[SubmissionRead]
    clarifications: list[ClarificationRead]


class SupplierAttachmentRead(BaseModel):
    document_version_id: UUID
    original_filename: str
    status: str


async def _view(context: SupplierContext) -> SupplierInvitationView:
    db = context.session
    invitation = await db.scalar(
        select(RfqInvitation).where(
            RfqInvitation.organization_id == context.organization_id,
            RfqInvitation.id == context.invitation_id,
            RfqInvitation.supplier_id == context.supplier_id,
        )
    )
    assert invitation is not None
    rfq = await db.scalar(
        select(Rfq).where(
            Rfq.organization_id == context.organization_id, Rfq.id == invitation.rfq_id
        )
    )
    assert rfq is not None
    if rfq.status is RfqStatus.DRAFT or invitation.rfq_revision_id is None:
        raise HTTPException(status_code=404, detail="Invitation is not yet published")
    items = list(
        await db.scalars(
            select(RfqItem)
            .where(RfqItem.organization_id == context.organization_id, RfqItem.rfq_id == rfq.id)
            .order_by(RfqItem.line_number)
        )
    )
    requirements = list(
        await db.scalars(
            select(RfqRequirement)
            .where(
                RfqRequirement.organization_id == context.organization_id,
                RfqRequirement.rfq_id == rfq.id,
            )
            .order_by(RfqRequirement.created_at)
        )
    )
    submission_ids = list(
        await db.scalars(
            select(QuoteSubmission.id)
            .where(
                QuoteSubmission.organization_id == context.organization_id,
                QuoteSubmission.invitation_id == invitation.id,
                QuoteSubmission.supplier_id == context.supplier_id,
            )
            .order_by(QuoteSubmission.version)
        )
    )
    clarifications = list(
        await db.scalars(
            select(RfqClarification)
            .where(
                RfqClarification.organization_id == context.organization_id,
                RfqClarification.rfq_id == rfq.id,
                (RfqClarification.visibility == ClarificationVisibility.SHARED)
                | (RfqClarification.invitation_id == invitation.id),
            )
            .order_by(RfqClarification.created_at)
        )
    )
    return SupplierInvitationView(
        organization_id=context.organization_id,
        invitation=InvitationRead.model_validate(invitation),
        rfq_id=rfq.id,
        title=rfq.title,
        currency=rfq.currency,
        submission_deadline=rfq.submission_deadline.isoformat(),
        status=rfq.status.value,
        version=rfq.version,
        publication_number=rfq.publication_number,
        terms=rfq.terms,
        items=[RfqItemRead.model_validate(item) for item in items],
        requirements=[RfqRequirementRead.model_validate(item) for item in requirements],
        submissions=[
            await read_submission(context.sourcing_context(), item) for item in submission_ids
        ],
        clarifications=[ClarificationRead.model_validate(item) for item in clarifications],
    )


@router.get("", response_model=SupplierInvitationView)
async def get_invitation(context: Principal) -> SupplierInvitationView:
    return await _view(context)


@router.post("/acknowledge", response_model=InvitationRead)
async def acknowledge(payload: InvitationAcknowledge, context: Principal) -> InvitationRead:
    return await execute(
        lambda: acknowledge_invitation(context.sourcing_context(), context.invitation_id, payload)
    )


@router.post("/no-bid", response_model=InvitationRead)
async def no_bid(payload: InvitationNoBid, context: Principal) -> InvitationRead:
    return await execute(
        lambda: decline_invitation(context.sourcing_context(), context.invitation_id, payload)
    )


@router.post("/submissions", response_model=SubmissionRead, status_code=status.HTTP_201_CREATED)
async def submit(payload: SubmissionCreate, context: Principal) -> SubmissionRead:
    if payload.document_version_ids:
        owned = set(
            await context.session.scalars(
                select(DocumentVersion.id)
                .join(
                    Document,
                    (Document.organization_id == DocumentVersion.organization_id)
                    & (Document.id == DocumentVersion.document_id),
                )
                .where(
                    DocumentVersion.organization_id == context.organization_id,
                    DocumentVersion.id.in_(payload.document_version_ids),
                    Document.document_type == _document_type(context.invitation_id),
                    Document.created_by_user_id == context.user_id,
                    DocumentVersion.status.in_(
                        {
                            DocumentVersionStatus.PARSING,
                            DocumentVersionStatus.PARSED,
                            DocumentVersionStatus.EXTRACTED,
                            DocumentVersionStatus.REVIEWED,
                        }
                    ),
                )
            )
        )
        if owned != set(payload.document_version_ids):
            raise HTTPException(
                status_code=422, detail="Attachment is not an available upload for this invitation"
            )
    return await execute(
        lambda: submit_quote(context.sourcing_context(), context.invitation_id, payload)
    )


def _document_type(invitation_id: UUID) -> str:
    return f"supplier_quote_{invitation_id.hex}"


@router.get("/documents", response_model=list[SupplierAttachmentRead])
async def list_own_attachments(context: Principal) -> list[SupplierAttachmentRead]:
    versions = list(
        await context.session.scalars(
            select(DocumentVersion)
            .join(
                Document,
                (Document.organization_id == DocumentVersion.organization_id)
                & (Document.id == DocumentVersion.document_id),
            )
            .where(
                DocumentVersion.organization_id == context.organization_id,
                Document.document_type == _document_type(context.invitation_id),
                Document.created_by_user_id == context.user_id,
            )
            .order_by(DocumentVersion.created_at.desc())
            .limit(100)
        )
    )
    return [
        SupplierAttachmentRead(
            document_version_id=item.id,
            original_filename=item.original_filename,
            status=item.status.value,
        )
        for item in versions
    ]


@router.post("/upload-intents", response_model=DocumentUploadIntentRead, status_code=201)
async def upload_intent(
    payload: DocumentUploadIntentCreate,
    context: Principal,
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentUploadIntentRead:
    await _view(context)
    scoped = payload.model_copy(update={"document_type": _document_type(context.invitation_id)})
    return await execute_document(
        lambda: create_upload_intent(context.sourcing_context(), settings, scoped)
    )


@router.post(
    "/documents/{document_id}/versions/{version_id}/complete-upload", response_model=DocumentRead
)
async def finish_upload(
    document_id: UUID,
    version_id: UUID,
    payload: DocumentUploadComplete,
    context: Principal,
    settings: Annotated[Settings, Depends(get_settings)],
    background_tasks: BackgroundTasks,
) -> DocumentRead:
    owned = await context.session.scalar(
        select(DocumentVersion.id)
        .join(
            Document,
            (Document.organization_id == DocumentVersion.organization_id)
            & (Document.id == DocumentVersion.document_id),
        )
        .where(
            DocumentVersion.organization_id == context.organization_id,
            DocumentVersion.document_id == document_id,
            DocumentVersion.id == version_id,
            Document.document_type == _document_type(context.invitation_id),
            Document.created_by_user_id == context.user_id,
        )
    )
    if owned is None:
        raise HTTPException(status_code=404, detail="Upload not available")
    result = await execute_document(
        lambda: complete_upload(
            context.sourcing_context(), settings, document_id, version_id, payload
        )
    )
    background_tasks.add_task(enqueue_document_scan, context.organization_id, version_id)
    return result


@router.get("/documents/{version_id}/download", response_model=DocumentDownloadRead)
async def download_own_attachment(
    version_id: UUID,
    context: Principal,
    settings: Annotated[Settings, Depends(get_settings)],
) -> DocumentDownloadRead:
    owned = await context.session.scalar(
        select(DocumentVersion.id)
        .join(
            Document,
            (Document.organization_id == DocumentVersion.organization_id)
            & (Document.id == DocumentVersion.document_id),
        )
        .where(
            DocumentVersion.organization_id == context.organization_id,
            DocumentVersion.id == version_id,
            Document.document_type == _document_type(context.invitation_id),
            Document.created_by_user_id == context.user_id,
        )
    )
    if owned is None:
        raise HTTPException(status_code=404, detail="Attachment not available")
    return await execute_document(
        lambda: create_download_url(context.sourcing_context(), settings, version_id)
    )


@router.post("/submissions/{submission_id}/withdraw", response_model=SubmissionRead)
async def withdraw(
    submission_id: UUID, payload: SubmissionWithdraw, context: Principal
) -> SubmissionRead:
    owned = await context.session.scalar(
        select(QuoteSubmission.id).where(
            QuoteSubmission.organization_id == context.organization_id,
            QuoteSubmission.invitation_id == context.invitation_id,
            QuoteSubmission.supplier_id == context.supplier_id,
            QuoteSubmission.id == submission_id,
        )
    )
    if owned is None:
        raise HTTPException(status_code=404, detail="Submission not available")
    return await execute(lambda: withdraw_quote(context.sourcing_context(), submission_id, payload))


class SupplierQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=5000)


@router.post(
    "/clarifications", response_model=ClarificationRead, status_code=status.HTTP_201_CREATED
)
async def ask(payload: SupplierQuestion, context: Principal) -> ClarificationRead:
    view = await _view(context)
    question = ClarificationCreate(
        invitation_id=context.invitation_id,
        visibility=ClarificationVisibility.PRIVATE,
        question=payload.question,
    )
    return await execute(
        lambda: create_clarification(context.sourcing_context(), view.rfq_id, question)
    )
