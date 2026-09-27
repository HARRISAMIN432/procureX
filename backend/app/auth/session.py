import hashlib
import hmac
from datetime import UTC, datetime

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.auth import AuthSession


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def load_auth_session(
    request: Request, settings: Settings, db: AsyncSession, *, require_csrf: bool = False
) -> AuthSession:
    raw_token = request.cookies.get(settings.auth_cookie_name)
    session: AuthSession | None = (
        await db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(raw_token)))
        if raw_token
        else None
    )
    now = datetime.now(UTC)
    if session is None or session.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "session_required", "message": "Sign-in session is missing or expired"},
        )
    if require_csrf:
        csrf = request.headers.get("X-CSRF-Token", "")
        if not csrf or not hmac.compare_digest(session.csrf_hash, digest(csrf)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "csrf_invalid", "message": "CSRF validation failed"},
            )
    session.last_seen_at = now
    return session
