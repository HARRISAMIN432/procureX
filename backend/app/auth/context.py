from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AuthMode, Settings, get_settings
from app.core.database import SessionFactory
from app.models.identity import (
    Membership,
    MembershipRole,
    MembershipStatus,
    Permission,
    RolePermission,
)


@dataclass(frozen=True, slots=True)
class RequestContext:
    organization_id: UUID
    user_id: UUID
    membership_id: UUID
    permissions: frozenset[str]
    session: AsyncSession


async def get_request_context(
    settings: Annotated[Settings, Depends(get_settings)],
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
    user_id: Annotated[UUID | None, Header(alias="X-User-ID")] = None,
) -> AsyncIterator[RequestContext]:
    """Resolve a principal and hold one transaction with its tenant RLS context."""
    if settings.auth_mode is not AuthMode.DEV_HEADERS:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={"code": "oidc_adapter_not_configured", "message": "OIDC adapter is pending"},
        )
    if organization_id is None or user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "development_identity_required",
                "message": "X-Organization-ID and X-User-ID are required in local mode",
            },
        )

    async with SessionFactory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :organization_id, true)"),
            {"organization_id": str(organization_id)},
        )
        membership_id = await session.scalar(
            select(Membership.id).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        if membership_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "membership_inactive", "message": "Active membership required"},
            )

        permission_codes = await session.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_code == Permission.code)
            .join(
                MembershipRole,
                (MembershipRole.organization_id == RolePermission.organization_id)
                & (MembershipRole.role_id == RolePermission.role_id),
            )
            .where(
                MembershipRole.organization_id == organization_id,
                MembershipRole.membership_id == membership_id,
            )
        )
        yield RequestContext(
            organization_id=organization_id,
            user_id=user_id,
            membership_id=membership_id,
            permissions=frozenset(permission_codes),
            session=session,
        )


PermissionDependency = Callable[..., Coroutine[Any, Any, RequestContext]]


def require_permission(permission: str) -> PermissionDependency:
    async def dependency(
        context: Annotated[RequestContext, Depends(get_request_context)],
    ) -> RequestContext:
        if permission not in context.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "permission_denied",
                    "message": f"Permission '{permission}' is required",
                },
            )
        return context

    return dependency
