from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth.oidc import OIDCAuthenticationError, authenticate_bearer_token
from app.core.config import AuthMode, Settings


class StaticKeyClient:
    def __init__(self, key: Any) -> None:
        self.key = key

    def get_signing_key_from_jwt(self, _: str) -> "StaticKeyClient":
        return self


def oidc_settings() -> Settings:
    return Settings(
        auth_mode=AuthMode.OIDC,
        oidc_issuer="https://identity.example.com",
        oidc_audience="procurex-api",
        oidc_jwks_url="https://identity.example.com/.well-known/jwks.json",
        _env_file=None,
    )


def token(private_key: Any, **overrides: object) -> str:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": "https://identity.example.com",
        "aud": "procurex-api",
        "sub": "provider-subject-123",
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


@pytest.mark.asyncio
async def test_oidc_verifies_signature_and_required_claims() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    principal = await authenticate_bearer_token(
        oidc_settings(),
        f"Bearer {token(private_key)}",
        key_client=StaticKeyClient(private_key.public_key()),
    )
    assert principal.subject == "provider-subject-123"


@pytest.mark.asyncio
async def test_oidc_only_trusts_email_marked_verified() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verified = await authenticate_bearer_token(
        oidc_settings(),
        f"Bearer {token(private_key, email='ADMIN@EXAMPLE.COM', email_verified=True)}",
        key_client=StaticKeyClient(private_key.public_key()),
    )
    unverified = await authenticate_bearer_token(
        oidc_settings(),
        f"Bearer {token(private_key, email='admin@example.com', email_verified=False)}",
        key_client=StaticKeyClient(private_key.public_key()),
    )
    assert verified.email == "admin@example.com"
    assert verified.email_verified is True
    assert unverified.email_verified is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "another-api"},
        {"iss": "https://attacker.example"},
        {"exp": datetime.now(UTC) - timedelta(minutes=5)},
        {"sub": ""},
    ],
)
async def test_oidc_rejects_invalid_claims(claims: dict[str, object]) -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(OIDCAuthenticationError):
        await authenticate_bearer_token(
            oidc_settings(),
            f"Bearer {token(private_key, **claims)}",
            key_client=StaticKeyClient(private_key.public_key()),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authorization",
    [None, "", "Basic abc", "Bearer", "Bearer " + "x" * 8193],
)
async def test_oidc_rejects_missing_or_malformed_authorization(
    authorization: str | None,
) -> None:
    with pytest.raises(OIDCAuthenticationError):
        await authenticate_bearer_token(
            oidc_settings(), authorization, key_client=StaticKeyClient(object())
        )


@pytest.mark.asyncio
async def test_oidc_rejects_wrong_signing_key() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(OIDCAuthenticationError):
        await authenticate_bearer_token(
            oidc_settings(),
            f"Bearer {token(private_key)}",
            key_client=StaticKeyClient(other_key.public_key()),
        )
