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
    assert settings.llm_provider == "gemini"
    assert settings.llm_model == "gemini-3.1-pro-preview"


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


def test_readiness_timeout_is_bounded() -> None:
    with pytest.raises(ValidationError):
        Settings(readiness_timeout_seconds=0, _env_file=None)
    with pytest.raises(ValidationError):
        Settings(readiness_timeout_seconds=31, _env_file=None)


def deployed_settings(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "environment": Environment.PRODUCTION,
        "auth_mode": AuthMode.OIDC,
        "oidc_issuer": "https://identity.example.com",
        "oidc_audience": "procurex-api",
        "cloudinary_cloud_name": "procurex",
        "cloudinary_api_key": "key",
        "cloudinary_api_secret": "secret",
        "gemini_api_key": "model-key",
        "allowed_hosts": ["api.procurex.example"],
        "cors_allowed_origins": ["https://app.procurex.example"],
        "_env_file": None,
    }
    values.update(overrides)
    return values


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"debug": True}, "disable debug"),
        ({"database_echo": True}, "statement logging"),
        ({"allowed_hosts": ["*"]}, "trusted hosts"),
        ({"allowed_hosts": ["*.procurex.example"]}, "trusted hosts"),
        ({"allowed_hosts": ["localhost"]}, "non-local trusted hosts"),
        ({"cors_allowed_origins": ["*"]}, "CORS origins"),
        ({"cors_allowed_origins": ["http://app.procurex.example"]}, "HTTPS origins"),
        ({"cors_allowed_origins": ["https://app.procurex.example/path"]}, "HTTPS origins"),
    ],
)
def test_deployed_settings_reject_unsafe_http_edge_configuration(
    override: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        Settings(**deployed_settings(**override))
