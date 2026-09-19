import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings


def test_local_settings_have_safe_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.environment is Environment.LOCAL
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.effective_langgraph_database_url.startswith("postgresql://")
    assert "+asyncpg" not in settings.effective_langgraph_database_url


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
