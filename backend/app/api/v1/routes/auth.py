import asyncio
import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.oidc import OIDCAuthenticationError, authenticate_id_token
from app.auth.session import digest, load_auth_session
from app.core.config import AuthMode, Environment, Settings, get_settings
from app.core.database import get_db_session
from app.models.auth import AuthLoginTransaction, AuthSession
from app.models.identity import User
from app.schemas.auth import BrowserSessionRead, WorkspaceSelection
from app.services.identity import list_principal_workspaces

router = APIRouter(prefix="/auth", tags=["authentication"])


def _require_oidc(settings: Settings) -> None:
    if settings.auth_mode is not AuthMode.OIDC:
        raise HTTPException(status_code=404, detail="Not found")
    if not all(
        (
            settings.oidc_authorization_url,
            settings.oidc_token_url,
            settings.effective_oidc_redirect_uri,
            settings.oidc_audience,
            settings.oidc_client_secret
            and settings.oidc_client_secret.get_secret_value().strip(),
        )
    ):
        raise HTTPException(status_code=503, detail="OIDC server flow is not configured")


def _cookie_secure(settings: Settings) -> bool:
    return settings.environment in {Environment.STAGING, Environment.PRODUCTION}


@router.get("/login")
async def login(
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> RedirectResponse:
    _require_oidc(settings)
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    async with db.begin():
        db.add(
            AuthLoginTransaction(
                state_hash=digest(state),
                nonce=nonce,
                code_verifier=verifier,
                expires_at=datetime.now(UTC) + timedelta(seconds=settings.auth_login_ttl_seconds),
            )
        )
    query = urlencode(
        {
            "client_id": settings.oidc_audience,
            "redirect_uri": settings.effective_oidc_redirect_uri,
            "response_type": "code",
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
    )
    return RedirectResponse(f"{settings.oidc_authorization_url}?{query}", status_code=302)


@router.get("/callback")
async def callback(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
    code: str = Query(min_length=1, max_length=4096),
    state_value: str = Query(alias="state", min_length=16, max_length=512),
) -> RedirectResponse:
    _require_oidc(settings)
    now = datetime.now(UTC)
    async with db.begin():
        transaction = await db.scalar(
            select(AuthLoginTransaction)
            .where(AuthLoginTransaction.state_hash == digest(state_value))
            .with_for_update()
        )
        if transaction is None or transaction.used or transaction.expires_at <= now:
            raise HTTPException(status_code=400, detail="OIDC state is invalid or expired")
        transaction.used = True
        verifier = transaction.code_verifier
        nonce = transaction.nonce

    secret = settings.oidc_client_secret
    assert secret is not None
    try:
        async with httpx.AsyncClient(timeout=settings.oidc_jwks_timeout_seconds) as client:
            token_response = await client.post(
                str(settings.oidc_token_url),
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": settings.oidc_audience,
                    "client_secret": secret.get_secret_value(),
                    "redirect_uri": settings.effective_oidc_redirect_uri,
                    "code_verifier": verifier,
                },
            )
        token_response.raise_for_status()
        id_token = token_response.json().get("id_token")
        if not isinstance(id_token, str):
            raise OIDCAuthenticationError("OIDC provider did not return an ID token")
        principal = await asyncio.to_thread(
            authenticate_id_token, settings, id_token, expected_nonce=nonce
        )
    except (httpx.HTTPError, ValueError, OIDCAuthenticationError) as exc:
        raise HTTPException(status_code=401, detail="OIDC code exchange failed") from exc

    raw_session = secrets.token_urlsafe(48)
    raw_csrf = secrets.token_urlsafe(32)
    async with db.begin():
        user = await db.scalar(select(User).where(User.external_subject == principal.subject))
        db.add(
            AuthSession(
                token_hash=digest(raw_session),
                csrf_hash=digest(raw_csrf),
                external_subject=principal.subject,
                email=principal.email,
                email_verified=principal.email_verified,
                user_id=user.id if user else None,
                expires_at=now + timedelta(seconds=settings.auth_session_ttl_seconds),
                last_seen_at=now,
            )
        )
        await db.execute(delete(AuthLoginTransaction).where(AuthLoginTransaction.expires_at <= now))
        await db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    response = RedirectResponse(
        f"{settings.web_app_url.rstrip('/')}/auth/callback", status_code=302
    )
    response.set_cookie(
        settings.auth_cookie_name,
        raw_session,
        httponly=True,
        secure=_cookie_secure(settings),
        samesite="lax",
        max_age=settings.auth_session_ttl_seconds,
        path="/",
    )
    response.set_cookie(
        settings.auth_csrf_cookie_name,
        raw_csrf,
        httponly=False,
        secure=_cookie_secure(settings),
        samesite="lax",
        max_age=settings.auth_session_ttl_seconds,
        path="/",
    )
    return response


@router.get("/session", response_model=BrowserSessionRead)
async def browser_session(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BrowserSessionRead:
    _require_oidc(settings)
    async with db.begin():
        session = await load_auth_session(request, settings, db)
        user = await db.scalar(
            select(User).where(User.external_subject == session.external_subject)
        )
        workspaces = await list_principal_workspaces(
            external_subject=session.external_subject,
            email=session.email,
            email_verified=session.email_verified,
        )
        available_ids = {workspace.organization_id for workspace in workspaces}
        selected = session.selected_organization_id
        if selected not in available_ids:
            selected = workspaces[0].organization_id if len(workspaces) == 1 else None
            session.selected_organization_id = selected
        csrf = request.cookies.get(settings.auth_csrf_cookie_name, "")
        if not csrf or digest(csrf) != session.csrf_hash:
            raise HTTPException(status_code=401, detail="Session CSRF token is missing")
        return BrowserSessionRead(
            authenticated=True,
            display_name=user.display_name if user else session.email or "ProcureX user",
            organization_id=selected,
            csrf_token=csrf,
            workspaces=workspaces,
        )


@router.post("/select-workspace", response_model=BrowserSessionRead)
async def select_workspace(
    payload: WorkspaceSelection,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> BrowserSessionRead:
    async with db.begin():
        session = await load_auth_session(request, settings, db, require_csrf=True)
        workspaces = await list_principal_workspaces(
            external_subject=session.external_subject,
            email=session.email,
            email_verified=session.email_verified,
        )
        if payload.organization_id not in {item.organization_id for item in workspaces}:
            raise HTTPException(status_code=403, detail="Workspace is not available")
        session.selected_organization_id = payload.organization_id
    return await browser_session(request, settings, db)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    db: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    async with db.begin():
        session = await load_auth_session(request, settings, db, require_csrf=True)
        await db.delete(session)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(settings.auth_cookie_name, path="/")
    response.delete_cookie(settings.auth_csrf_cookie_name, path="/")
    return response
