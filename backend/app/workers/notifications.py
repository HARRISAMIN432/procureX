import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import close_database, tenant_transaction
from app.core.email import EmailDeliveryError, ResendEmailClient, RetryableEmailDeliveryError
from app.models.identity import Membership, MembershipStatus, Organization, User
from app.models.platform import ActorType, AuditEvent
from app.workers.celery_app import celery_app


def enqueue_invitation_email(organization_id: uuid.UUID, membership_id: uuid.UUID) -> None:
    send_invitation_email.apply_async(args=[str(organization_id), str(membership_id)])


async def _deliver_invitation(
    organization_id: uuid.UUID, membership_id: uuid.UUID
) -> dict[str, object]:
    async with tenant_transaction(organization_id) as session:
        membership = await session.scalar(
            select(Membership)
            .where(
                Membership.organization_id == organization_id,
                Membership.id == membership_id,
            )
            .with_for_update()
        )
        if membership is None:
            raise ValueError("Invitation membership not found")
        if membership.invitation_email_status == "sent":
            return {"status": "sent", "membership_id": str(membership_id)}
        if membership.status not in {MembershipStatus.INVITED, MembershipStatus.ACTIVE}:
            raise ValueError("Invitation membership is inactive")
        user = await session.get(User, membership.user_id)
        organization = await session.get(Organization, organization_id)
        inviter = (
            await session.get(User, membership.invited_by_user_id)
            if membership.invited_by_user_id
            else None
        )
        if user is None or organization is None:
            raise ValueError("Invitation email input not found")
        membership.invitation_email_status = "sending"
        membership.invitation_email_attempts += 1
        membership.invitation_email_error_code = None
        recipient_email = user.email
        recipient_name = user.display_name
        organization_name = organization.name
        inviter_name = inviter.display_name if inviter else organization.name

    try:
        result = await asyncio.to_thread(
            ResendEmailClient(get_settings()).send_invitation,
            recipient_email=recipient_email,
            recipient_name=recipient_name,
            organization_name=organization_name,
            invited_by_name=inviter_name,
            idempotency_key=f"member-invitation/{membership_id}",
        )
    except Exception as exc:
        retryable = isinstance(exc, EmailDeliveryError) and exc.retryable
        async with tenant_transaction(organization_id) as session:
            membership = await session.scalar(
                select(Membership)
                .where(
                    Membership.organization_id == organization_id,
                    Membership.id == membership_id,
                )
                .with_for_update()
            )
            if membership is not None:
                exhausted = membership.invitation_email_attempts >= 3 or not retryable
                membership.invitation_email_status = "failed" if exhausted else "retry_scheduled"
                membership.invitation_email_error_code = (
                    exc.code if isinstance(exc, EmailDeliveryError) else type(exc).__name__[:100]
                )
        raise

    async with tenant_transaction(organization_id) as session:
        membership = await session.scalar(
            select(Membership)
            .where(
                Membership.organization_id == organization_id,
                Membership.id == membership_id,
            )
            .with_for_update()
        )
        if membership is None:
            raise ValueError("Invitation membership not found after delivery")
        membership.invitation_email_status = "sent"
        membership.invitation_email_provider_id = result.provider_message_id
        membership.invitation_email_sent_at = datetime.now(UTC)
        membership.invitation_email_error_code = None
        session.add(
            AuditEvent(
                organization_id=organization_id,
                actor_type=ActorType.SERVICE,
                action="organization.invitation_email_sent",
                object_type="membership",
                object_id=membership.id,
                object_version=membership.invitation_email_attempts,
                changes={"provider": "resend"},
            )
        )
    return {"status": "sent", "membership_id": str(membership_id)}


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    name="procurex.invitation_email",
    autoretry_for=(RetryableEmailDeliveryError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
    ignore_result=True,
)
def send_invitation_email(_: Any, organization_id: str, membership_id: str) -> dict[str, object]:
    async def execute_and_close() -> dict[str, object]:
        try:
            return await _deliver_invitation(uuid.UUID(organization_id), uuid.UUID(membership_id))
        finally:
            await close_database()

    return asyncio.run(execute_and_close())
