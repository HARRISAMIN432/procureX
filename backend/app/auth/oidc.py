import asyncio
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol, cast

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKClientError, PyJWTError

from app.core.config import Settings


class OIDCAuthenticationError(ValueError):
    pass


class SigningKey(Protocol):
    key: Any


class SigningKeyClient(Protocol):
    def get_signing_key_from_jwt(self, token: str) -> SigningKey: ...


@dataclass(frozen=True, slots=True)
class OIDCPrincipal:
    subject: str
    email: str | None = None
    email_verified: bool = False


@lru_cache(maxsize=16)
def jwks_client(url: str, timeout_seconds: float) -> PyJWKClient:
    return PyJWKClient(
        url,
        cache_keys=True,
        cache_jwk_set=True,
        lifespan=300,
        timeout=timeout_seconds,
    )


def _decode_token(settings: Settings, token: str, key_client: SigningKeyClient) -> OIDCPrincipal:
    if not settings.oidc_issuer or not settings.oidc_audience:
        raise OIDCAuthenticationError("OIDC verifier is not configured")
    try:
        signing_key = key_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key=signing_key.key,
            algorithms=settings.oidc_algorithms,
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            leeway=settings.oidc_clock_skew_seconds,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
    except (PyJWTError, PyJWKClientError, ValueError, TypeError) as exc:
        raise OIDCAuthenticationError("Bearer token is invalid") from exc
    subject = cast(object, claims.get("sub"))
    if not isinstance(subject, str) or not subject.strip() or len(subject) > 255:
        raise OIDCAuthenticationError("Bearer token subject is invalid")
    email_claim = claims.get("email")
    email = (
        email_claim.strip().lower()
        if isinstance(email_claim, str) and email_claim.strip() and len(email_claim) <= 320
        else None
    )
    return OIDCPrincipal(
        subject=subject,
        email=email,
        email_verified=email is not None and claims.get("email_verified") is True,
    )


async def authenticate_bearer_token(
    settings: Settings,
    authorization: str | None,
    *,
    key_client: SigningKeyClient | None = None,
) -> OIDCPrincipal:
    if not authorization:
        raise OIDCAuthenticationError("Bearer token is required")
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token or len(token) > 8192:
        raise OIDCAuthenticationError("Bearer token is malformed")
    if not settings.oidc_jwks_url and key_client is None:
        raise OIDCAuthenticationError("OIDC verifier is not configured")
    client = key_client or jwks_client(
        cast(str, settings.oidc_jwks_url), settings.oidc_jwks_timeout_seconds
    )
    return await asyncio.to_thread(_decode_token, settings, token, client)
