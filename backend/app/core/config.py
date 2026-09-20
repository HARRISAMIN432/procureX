from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class AuthMode(StrEnum):
    DEV_HEADERS = "dev_headers"
    OIDC = "oidc"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PROCUREX_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "ProcureX API"
    api_v1_prefix: str = "/api/v1"
    environment: Environment = Environment.LOCAL
    debug: bool = False

    auth_mode: AuthMode = AuthMode.DEV_HEADERS
    dev_bootstrap_key: SecretStr = SecretStr("local-development-only")
    oidc_issuer: str | None = None
    oidc_audience: str | None = None

    database_url: str = "postgresql+asyncpg://procurex:procurex@localhost:5432/procurex"
    database_echo: bool = False
    database_pool_size: int = 10
    database_max_overflow: int = 20

    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: SecretStr | None = None
    cloudinary_api_secret: SecretStr | None = None
    cloudinary_folder_prefix: str = "procurex/local"
    document_max_upload_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    document_upload_intent_ttl_seconds: int = Field(default=10 * 60, ge=60, le=3600)
    document_download_ttl_seconds: int = Field(default=5 * 60, ge=60, le=900)

    rabbitmq_url: SecretStr = SecretStr("amqp://procurex:procurex@localhost:5672//")
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")

    langgraph_checkpoint_database_url: SecretStr | None = None
    llm_provider: str = "gemini"
    llm_model: str = "gemini-3.1-pro-preview"
    gemini_api_key: SecretStr | None = None
    llm_timeout_seconds: float = Field(default=90, gt=0, le=300)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    evaluation_evidence_limit: int = Field(default=120, gt=0, le=500)
    evaluation_evidence_max_chars: int = Field(default=60_000, ge=1_000, le=500_000)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_langgraph_database_url(self) -> str:
        if self.langgraph_checkpoint_database_url is not None:
            configured_url = self.langgraph_checkpoint_database_url.get_secret_value().strip()
            if configured_url:
                return configured_url
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    @model_validator(mode="after")
    def validate_deployed_secrets(self) -> "Settings":
        if self.environment in {Environment.STAGING, Environment.PRODUCTION}:
            missing = [
                name
                for name, value in (
                    ("cloudinary_cloud_name", self.cloudinary_cloud_name),
                    ("cloudinary_api_key", self.cloudinary_api_key),
                    ("cloudinary_api_secret", self.cloudinary_api_secret),
                )
                if value is None
                or (isinstance(value, str) and not value.strip())
                or (isinstance(value, SecretStr) and not value.get_secret_value().strip())
            ]
            if missing:
                raise ValueError(f"Missing deployed-environment settings: {', '.join(missing)}")
            if self.auth_mode is not AuthMode.OIDC:
                raise ValueError("Staging and production require PROCUREX_AUTH_MODE=oidc")
            if not self.oidc_issuer or not self.oidc_audience:
                raise ValueError("Staging and production require OIDC issuer and audience")
            if self.llm_provider != "gemini":
                raise ValueError("Staging and production require PROCUREX_LLM_PROVIDER=gemini")
            if self.gemini_api_key is None or not self.gemini_api_key.get_secret_value().strip():
                raise ValueError("Staging and production require PROCUREX_GEMINI_API_KEY")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
