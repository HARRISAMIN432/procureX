from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select

from app.auth.context import RequestContext, require_permission
from app.auth.oidc import OIDCAuthenticationError, authenticate_bearer_token
from app.core.config import AuthMode, Environment, Settings, get_settings
from app.models.identity import Organization, OrganizationSetting
from app.schemas.identity import (
    MemberInviteCreate,
    MemberRead,
    MembershipContextRead,
    MembershipUpdate,
    OrganizationBootstrapRequest,
    OrganizationBootstrapResponse,
    OrganizationRead,
    OrganizationSettingsRead,
    OrganizationSettingsWrite,
    OrganizationSignupRequest,
    OrganizationWorkspaceRead,
    RoleCreate,
    RoleRead,
)
from app.services.identity import (
    BootstrapDeniedError,
    IdentityConflictError,
    IdentityNotFoundError,
    SlugAlreadyExistsError,
    bootstrap_organization,
    create_organization_settings,
    create_role,
    invite_member,
    list_members,
    list_principal_workspaces,
    list_roles,
    update_membership,
    verify_bootstrap_key,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/mine", response_model=list[OrganizationWorkspaceRead])
async def principal_workspaces(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> list[OrganizationWorkspaceRead]:
    """Return selectable workspaces for a verified OIDC principal.

    This endpoint intentionally does not accept a tenant header: it is the narrow pre-tenant
    identity lookup used after provider sign-in. It never returns other users' memberships.
    """
    if settings.auth_mode is not AuthMode.OIDC:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        principal = await authenticate_bearer_token(settings, authorization)
        return await list_principal_workspaces(
            external_subject=principal.subject,
            email=principal.email,
            email_verified=principal.email_verified,
        )
    except OIDCAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_bearer_token", "message": str(exc)},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.post("", response_model=OrganizationBootstrapResponse, status_code=status.HTTP_201_CREATED)
async def oidc_organization_signup(
    payload: OrganizationSignupRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> OrganizationBootstrapResponse:
    if (
        settings.auth_mode is not AuthMode.OIDC
        or not settings.allow_self_service_organization_signup
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        principal = await authenticate_bearer_token(settings, authorization)
        if not principal.email_verified or principal.email is None:
            raise OIDCAuthenticationError("A verified email claim is required")
        if str(payload.admin_email).lower() != principal.email:
            raise OIDCAuthenticationError("Signup email must match the verified bearer identity")
        return await bootstrap_organization(payload, external_subject=principal.subject)
    except OIDCAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_bearer_token", "message": str(exc)},
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except (SlugAlreadyExistsError, IdentityConflictError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "organization_signup_conflict", "message": str(exc)},
        ) from exc


@router.post(
    "/dev-bootstrap",
    response_model=OrganizationBootstrapResponse,
    status_code=status.HTTP_201_CREATED,
)
async def development_bootstrap(
    payload: OrganizationBootstrapRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    bootstrap_key: Annotated[str | None, Header(alias="X-Dev-Bootstrap-Key")] = None,
) -> OrganizationBootstrapResponse:
    if settings.environment not in {Environment.LOCAL, Environment.TEST}:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if settings.auth_mode is not AuthMode.DEV_HEADERS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    try:
        verify_bootstrap_key(settings, bootstrap_key)
        return await bootstrap_organization(payload)
    except BootstrapDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_bootstrap_key", "message": str(exc)},
        ) from exc
    except SlugAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "organization_slug_exists", "message": str(exc)},
        ) from exc


@router.get("/current", response_model=OrganizationRead)
async def current_organization(
    context: Annotated[RequestContext, Depends(require_permission("organization.read"))],
) -> Organization:
    organization = await context.session.get(Organization, context.organization_id)
    if organization is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return organization


@router.get("/current/membership", response_model=MembershipContextRead)
async def current_membership(
    context: Annotated[RequestContext, Depends(require_permission("organization.read"))],
) -> MembershipContextRead:
    return MembershipContextRead(
        organization_id=context.organization_id,
        user_id=context.user_id,
        membership_id=context.membership_id,
        permissions=sorted(context.permissions),
    )


@router.get("/current/roles", response_model=list[RoleRead])
async def roles(
    context: Annotated[RequestContext, Depends(require_permission("organization.members.read"))],
) -> list[RoleRead]:
    return await list_roles(context)


@router.post("/current/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
async def add_role(
    payload: RoleCreate,
    context: Annotated[RequestContext, Depends(require_permission("organization.members.manage"))],
) -> RoleRead:
    try:
        return await create_role(context, payload)
    except IdentityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "permission_not_found", "message": str(exc)},
        ) from exc
    except IdentityConflictError as exc:
        raise HTTPException(
            status_code=409, detail={"code": "role_conflict", "message": str(exc)}
        ) from exc


@router.get("/current/members", response_model=list[MemberRead])
async def members(
    context: Annotated[RequestContext, Depends(require_permission("organization.members.read"))],
) -> list[MemberRead]:
    return await list_members(context)


@router.post("/current/members", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
async def add_member(
    payload: MemberInviteCreate,
    context: Annotated[RequestContext, Depends(require_permission("organization.members.manage"))],
) -> MemberRead:
    try:
        return await invite_member(context, payload)
    except IdentityNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail={"code": "role_not_found", "message": str(exc)}
        ) from exc
    except IdentityConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "membership_conflict", "message": str(exc)},
        ) from exc


@router.patch("/current/members/{membership_id}", response_model=MemberRead)
async def change_member(
    membership_id: UUID,
    payload: MembershipUpdate,
    context: Annotated[RequestContext, Depends(require_permission("organization.members.manage"))],
) -> MemberRead:
    try:
        return await update_membership(context, membership_id, payload)
    except IdentityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "membership_not_found", "message": str(exc)},
        ) from exc
    except IdentityConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "membership_conflict", "message": str(exc)},
        ) from exc


@router.get("/current/settings", response_model=OrganizationSettingsRead)
async def current_settings(
    context: Annotated[RequestContext, Depends(require_permission("organization.settings.read"))],
) -> OrganizationSetting:
    setting = await context.session.scalar(
        select(OrganizationSetting)
        .where(
            OrganizationSetting.organization_id == context.organization_id,
            OrganizationSetting.effective_to.is_(None),
        )
        .order_by(OrganizationSetting.version.desc())
        .limit(1)
    )
    if setting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "settings_not_found", "message": "No settings version exists"},
        )
    return setting


@router.put(
    "/current/settings",
    response_model=OrganizationSettingsRead,
    status_code=status.HTTP_201_CREATED,
)
async def replace_settings(
    payload: OrganizationSettingsWrite,
    context: Annotated[RequestContext, Depends(require_permission("organization.settings.write"))],
) -> OrganizationSetting:
    try:
        return await create_organization_settings(context, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "invalid_effective_time", "message": str(exc)},
        ) from exc
