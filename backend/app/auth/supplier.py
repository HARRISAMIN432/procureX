"""Invitation-scoped supplier principal. This never grants a buyer membership."""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.context import RequestContext
from app.auth.session import load_auth_session
from app.core.config import AuthMode, Settings, get_settings
from app.core.database import SessionFactory
from app.models.identity import Organization, OrganizationStatus, User, UserStatus
from app.models.operations import PurchaseOrder
from app.models.sourcing import InvitationStatus, RfqInvitation
from app.models.suppliers import Supplier, SupplierContact, SupplierStatus


@dataclass(frozen=True, slots=True)
class SupplierContext:
    organization_id: UUID
    invitation_id: UUID
    supplier_id: UUID
    user_id: UUID
    session: AsyncSession

    def sourcing_context(self) -> RequestContext:
        # Existing sourcing commands require an actor and tenant session, but
        # supplier routes never use buyer permission dependencies.
        return RequestContext(
            self.organization_id, self.user_id, UUID(int=0), frozenset(), self.session
        )


@dataclass(frozen=True, slots=True)
class SupplierOrderContext:
    organization_id: UUID
    purchase_order_id: UUID
    supplier_id: UUID
    user_id: UUID
    session: AsyncSession

    def operation_context(self) -> RequestContext:
        return RequestContext(
            self.organization_id, self.user_id, UUID(int=0), frozenset(), self.session
        )


async def _user_for_contact(session: AsyncSession, email: str, subject: str) -> User:
    user = await session.scalar(select(User).where(User.external_subject == subject))
    if user is None:
        user = await session.scalar(
            select(User).where(func.lower(User.email) == email.lower()).with_for_update()
        )
        if user is not None and user.external_subject is not None:
            raise HTTPException(status_code=403, detail="Contact identity does not match")
        if user is None:
            user = User(
                email=email.lower(),
                display_name=email.split("@")[0],
                external_subject=subject,
                status=UserStatus.ACTIVE,
            )
            session.add(user)
        else:
            user.external_subject = subject
            user.status = UserStatus.ACTIVE
        await session.flush()
    if user.status is not UserStatus.ACTIVE or user.email.lower() != email.lower():
        raise HTTPException(status_code=403, detail="Contact identity is inactive")
    user.last_login_at = datetime.now(UTC)
    return user


async def get_supplier_context(
    request: Request,
    organization_id: UUID,
    invitation_id: UUID,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[SupplierContext]:
    if settings.auth_mode is not AuthMode.OIDC:
        raise HTTPException(status_code=404, detail="Supplier access requires configured sign-in")
    async with SessionFactory() as session, session.begin():
        identity = await load_auth_session(
            request,
            settings,
            session,
            require_csrf=request.method not in {"GET", "HEAD", "OPTIONS"},
        )
        if not identity.email_verified or not identity.email:
            raise HTTPException(
                status_code=403, detail="A verified supplier contact email is required"
            )
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :organization_id, true)"),
            {"organization_id": str(organization_id)},
        )
        organization = await session.scalar(
            select(Organization.status).where(Organization.id == organization_id)
        )
        if organization is not OrganizationStatus.ACTIVE:
            raise HTTPException(status_code=404, detail="Invitation not available")
        invitation = await session.scalar(
            select(RfqInvitation).where(
                RfqInvitation.organization_id == organization_id,
                RfqInvitation.id == invitation_id,
                RfqInvitation.status != InvitationStatus.REVOKED,
            )
        )
        if invitation is None:
            raise HTTPException(status_code=404, detail="Invitation not available")
        supplier = await session.scalar(
            select(Supplier.status).where(
                Supplier.organization_id == organization_id,
                Supplier.id == invitation.supplier_id,
            )
        )
        contact = await session.scalar(
            select(SupplierContact.id).where(
                SupplierContact.organization_id == organization_id,
                SupplierContact.supplier_id == invitation.supplier_id,
                func.lower(SupplierContact.email) == identity.email.lower(),
            )
        )
        if supplier is not SupplierStatus.APPROVED or contact is None:
            raise HTTPException(status_code=404, detail="Invitation not available")
        user = await _user_for_contact(session, identity.email, identity.external_subject)
        yield SupplierContext(
            organization_id, invitation_id, invitation.supplier_id, user.id, session
        )


async def get_supplier_order_context(
    request: Request,
    organization_id: UUID,
    purchase_order_id: UUID,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[SupplierOrderContext]:
    if settings.auth_mode is not AuthMode.OIDC:
        raise HTTPException(status_code=404, detail="Supplier access requires configured sign-in")
    async with SessionFactory() as session, session.begin():
        identity = await load_auth_session(
            request,
            settings,
            session,
            require_csrf=request.method not in {"GET", "HEAD", "OPTIONS"},
        )
        if not identity.email_verified or not identity.email:
            raise HTTPException(status_code=403, detail="Verified supplier contact email required")
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :organization_id, true)"),
            {"organization_id": str(organization_id)},
        )
        organization = await session.scalar(
            select(Organization.status).where(Organization.id == organization_id)
        )
        if organization is not OrganizationStatus.ACTIVE:
            raise HTTPException(status_code=404, detail="Order not available")
        order = await session.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.organization_id == organization_id,
                PurchaseOrder.id == purchase_order_id,
            )
        )
        if order is None:
            raise HTTPException(status_code=404, detail="Order not available")
        contact = await session.scalar(
            select(SupplierContact.id).where(
                SupplierContact.organization_id == organization_id,
                SupplierContact.supplier_id == order.supplier_id,
                func.lower(SupplierContact.email) == identity.email.lower(),
            )
        )
        if contact is None:
            raise HTTPException(status_code=404, detail="Order not available")
        user = await _user_for_contact(session, identity.email, identity.external_subject)
        yield SupplierOrderContext(
            organization_id, purchase_order_id, order.supplier_id, user.id, session
        )
