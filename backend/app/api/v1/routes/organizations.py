from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select

from app.auth.context import RequestContext, require_permission
from app.core.config import AuthMode, Environment, Settings, get_settings
from app.models.identity import Organization, OrganizationSetting
from app.schemas.identity import (
    MembershipContextRead,
    OrganizationBootstrapRequest,
    OrganizationBootstrapResponse,
    OrganizationRead,
    OrganizationSettingsRead,
    OrganizationSettingsWrite,
)
from app.services.identity import (
    BootstrapDeniedError,
    SlugAlreadyExistsError,
    bootstrap_organization,
    create_organization_settings,
    verify_bootstrap_key,
)

router = APIRouter(prefix="/organizations", tags=["organizations"])


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
