import pytest
from pydantic import ValidationError

from app.core.config import AuthMode, Environment, Settings


def test_local_settings_have_safe_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.environment is Environment.LOCAL
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.effective_langgraph_database_url.startswith("postgresql://")
    assert "+asyncpg" not in settings.effective_langgraph_database_url
    assert settings.document_max_upload_bytes == 25 * 1024 * 1024
    assert settings.document_upload_intent_ttl_seconds == 600


def test_production_requires_cloudinary_credentials() -> None:
    with pytest.raises(ValidationError, match="cloudinary_cloud_name"):
        Settings(environment=Environment.PRODUCTION, _env_file=None)


def test_production_rejects_blank_cloudinary_secrets() -> None:
    with pytest.raises(ValidationError, match="cloudinary_api_key"):
        Settings(
            environment=Environment.PRODUCTION,
            cloudinary_cloud_name="procurex",
            cloudinary_api_key="",
            cloudinary_api_secret="",
            _env_file=None,
        )


def test_production_rejects_development_header_auth() -> None:
    with pytest.raises(ValidationError, match="AUTH_MODE=oidc"):
        Settings(
            environment=Environment.PRODUCTION,
            auth_mode=AuthMode.DEV_HEADERS,
            cloudinary_cloud_name="procurex",
            cloudinary_api_key="key",
            cloudinary_api_secret="secret",
            _env_file=None,
        )


def test_document_intake_limits_must_be_safe() -> None:
    with pytest.raises(ValidationError):
        Settings(document_max_upload_bytes=0, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(document_upload_intent_ttl_seconds=30, _env_file=None)
