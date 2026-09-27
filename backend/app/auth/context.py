from collections.abc import AsyncIterator, Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import load_auth_session
from app.core.config import AuthMode, Settings, get_settings
from app.core.database import SessionFactory
from app.models.identity import (
    Membership,
    MembershipRole,
    MembershipStatus,
    Organization,
    OrganizationStatus,
    Permission,
    RolePermission,
    User,
    UserStatus,
)


@dataclass(frozen=True, slots=True)
class RequestContext:
    organization_id: UUID
    user_id: UUID
    membership_id: UUID
    permissions: frozenset[str]
    session: AsyncSession


async def get_request_context(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    organization_id: Annotated[UUID | None, Header(alias="X-Organization-ID")] = None,
    user_id: Annotated[UUID | None, Header(alias="X-User-ID")] = None,
) -> AsyncIterator[RequestContext]:
    """Resolve a principal and hold one transaction with its tenant RLS context."""
    if organization_id is None and settings.auth_mode is AuthMode.DEV_HEADERS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "organization_context_required",
                "message": "X-Organization-ID is required",
            },
        )

    async with SessionFactory() as session, session.begin():
        if settings.auth_mode is AuthMode.DEV_HEADERS:
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail={
                        "code": "development_identity_required",
                        "message": "X-User-ID is required in local mode",
                    },
                )
        else:
            auth_session = await load_auth_session(
                request,
                settings,
                session,
                require_csrf=request.method not in {"GET", "HEAD", "OPTIONS"},
            )
            if auth_session.selected_organization_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "workspace_required", "message": "Select a workspace"},
                )
            if (
                organization_id is not None
                and organization_id != auth_session.selected_organization_id
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={"code": "workspace_mismatch", "message": "Workspace context mismatch"},
                )
            organization_id = auth_session.selected_organization_id
            principal_subject = auth_session.external_subject
            user = await session.scalar(
                select(User).where(
                    User.external_subject == principal_subject,
                    User.status == UserStatus.ACTIVE,
                )
            )
            if user is None and auth_session.email_verified and auth_session.email is not None:
                invited = await session.scalar(
                    select(User)
                    .join(Membership, Membership.user_id == User.id)
                    .where(
                        Membership.organization_id == organization_id,
                        Membership.status == MembershipStatus.INVITED,
                        func.lower(User.email) == auth_session.email,
                        User.status == UserStatus.INVITED,
                        User.external_subject.is_(None),
                    )
                    .with_for_update()
                )
                if invited is not None:
                    invited.external_subject = principal_subject
                    invited.status = UserStatus.ACTIVE
                    invited.last_login_at = datetime.now(UTC)
                    invited_membership = await session.scalar(
                        select(Membership)
                        .where(
                            Membership.organization_id == organization_id,
                            Membership.user_id == invited.id,
                            Membership.status == MembershipStatus.INVITED,
                        )
                        .with_for_update()
                    )
                    assert invited_membership is not None
                    invited_membership.status = MembershipStatus.ACTIVE
                    invited_membership.joined_at = datetime.now(UTC)
                    user = invited
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "principal_not_provisioned",
                        "message": "Authenticated principal has no active ProcureX user",
                    },
                )
            user_id = user.id
            auth_session.user_id = user.id
        assert organization_id is not None
        assert user_id is not None
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :organization_id, true)"),
            {"organization_id": str(organization_id)},
        )
        organization_status = await session.scalar(
            select(Organization.status).where(Organization.id == organization_id)
        )
        if organization_status in {OrganizationStatus.SUSPENDED, OrganizationStatus.CLOSED}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "organization_inactive",
                    "message": "Organization access is suspended or closed",
                },
            )
        membership_id = await session.scalar(
            select(Membership.id).where(
                Membership.organization_id == organization_id,
                Membership.user_id == user_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        if membership_id is None and settings.auth_mode is AuthMode.OIDC:
            invited_membership = await session.scalar(
                select(Membership)
                .where(
                    Membership.organization_id == organization_id,
                    Membership.user_id == user_id,
                    Membership.status == MembershipStatus.INVITED,
                )
                .with_for_update()
            )
            if invited_membership is not None:
                invited_membership.status = MembershipStatus.ACTIVE
                invited_membership.joined_at = datetime.now(UTC)
                membership_id = invited_membership.id
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
