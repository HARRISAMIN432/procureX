"""Revision-aware supplier invitation email delivery."""

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.config import EmailProvider, get_settings
from app.core.database import close_database, tenant_transaction
from app.core.email import EmailDeliveryError, ResendEmailClient, RetryableEmailDeliveryError
from app.models.identity import Organization
from app.models.platform import ActorType, AuditEvent
from app.models.sourcing import Rfq, RfqInvitation, RfqStatus
from app.models.suppliers import SupplierContact
from app.workers.celery_app import celery_app


def enqueue_supplier_invitation_email(
    organization_id: uuid.UUID, invitation_id: uuid.UUID, publication_number: int
) -> None:
    if get_settings().email_provider is EmailProvider.DISABLED:
        return
    send_supplier_invitation_email.apply_async(
        args=[str(organization_id), str(invitation_id), publication_number]
    )


async def _deliver(
    organization_id: uuid.UUID, invitation_id: uuid.UUID, publication_number: int
) -> dict[str, object]:
    async with tenant_transaction(organization_id) as session:
        invitation = await session.scalar(
            select(RfqInvitation)
            .where(
                RfqInvitation.organization_id == organization_id,
                RfqInvitation.id == invitation_id,
            )
            .with_for_update()
        )
        if invitation is None:
            raise ValueError("Supplier invitation not found")
        rfq = await session.scalar(
            select(Rfq).where(
                Rfq.organization_id == organization_id,
                Rfq.id == invitation.rfq_id,
            )
        )
        if rfq is None or rfq.status is not RfqStatus.PUBLISHED:
            return {"status": "not_open"}
        if (
            invitation.email_publication_number != publication_number
            or rfq.publication_number != publication_number
        ):
            return {"status": "stale_publication"}
        if invitation.email_status == "sent":
            return {"status": "sent", "invitation_id": str(invitation_id)}
        contact = await session.scalar(
            select(SupplierContact)
            .where(
                SupplierContact.organization_id == organization_id,
                SupplierContact.supplier_id == invitation.supplier_id,
            )
            .order_by(
                SupplierContact.is_primary.desc(), SupplierContact.created_at, SupplierContact.id
            )
        )
        organization = await session.scalar(
            select(Organization).where(Organization.id == organization_id)
        )
        if contact is None or organization is None:
            invitation.email_status = "failed"
            invitation.email_error_code = "contact_missing"
            return {"status": "failed", "reason": "contact_missing"}
        invitation.email_status = "sending"
        invitation.email_attempts += 1
        invitation.email_error_code = None
        recipient_email = contact.email
        recipient_name = contact.name
        organization_name = organization.name
        rfq_title = rfq.title
        deadline = rfq.submission_deadline.isoformat()

    try:
        result = await asyncio.to_thread(
            ResendEmailClient(get_settings()).send_supplier_invitation,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            organization_name=organization_name,
            rfq_title=rfq_title,
            deadline=deadline,
            organization_id=organization_id,
            invitation_id=invitation_id,
            publication_number=publication_number,
        )
    except Exception as exc:
        retryable = isinstance(exc, EmailDeliveryError) and exc.retryable
        async with tenant_transaction(organization_id) as session:
            invitation = await session.scalar(
                select(RfqInvitation)
                .where(
                    RfqInvitation.organization_id == organization_id,
                    RfqInvitation.id == invitation_id,
                )
                .with_for_update()
            )
            if invitation is not None and invitation.email_publication_number == publication_number:
                invitation.email_status = (
                    "retry_scheduled" if retryable and invitation.email_attempts < 3 else "failed"
                )
                invitation.email_error_code = (
                    exc.code if isinstance(exc, EmailDeliveryError) else type(exc).__name__[:100]
                )
        raise

    async with tenant_transaction(organization_id) as session:
        invitation = await session.scalar(
            select(RfqInvitation)
            .where(
                RfqInvitation.organization_id == organization_id,
                RfqInvitation.id == invitation_id,
            )
            .with_for_update()
        )
        if invitation is None or invitation.email_publication_number != publication_number:
            return {"status": "stale_publication"}
        invitation.email_status = "sent"
        invitation.email_provider_id = result.provider_message_id
        invitation.email_sent_at = datetime.now(UTC)
        invitation.email_error_code = None
        session.add(
            AuditEvent(
                organization_id=organization_id,
                actor_type=ActorType.SERVICE,
                action="rfq.supplier_invitation_email_sent",
                object_type="rfq_invitation",
                object_id=invitation.id,
                object_version=publication_number,
                changes={"provider": "resend", "publication_number": publication_number},
            )
        )
    return {"status": "sent", "invitation_id": str(invitation_id)}


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="procurex.supplier_invitation_email",
    autoretry_for=(RetryableEmailDeliveryError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
    ignore_result=True,
)
def send_supplier_invitation_email(
    _: Any, organization_id: str, invitation_id: str, publication_number: int
) -> dict[str, object]:
    async def run() -> dict[str, object]:
        try:
            return await _deliver(
                uuid.UUID(organization_id), uuid.UUID(invitation_id), publication_number
            )
        finally:
            await close_database()

    return asyncio.run(run())
