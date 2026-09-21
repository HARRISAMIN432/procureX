import sys
from enum import StrEnum
from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class AuthMode(StrEnum):
    DEV_HEADERS = "dev_headers"
    OIDC = "oidc"


class TaskExecutionMode(StrEnum):
    BROKER = "broker"
    EAGER = "eager"


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
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"]
    )
    cors_allowed_origins: list[str] = Field(default_factory=list)

    auth_mode: AuthMode = AuthMode.DEV_HEADERS
    dev_bootstrap_key: SecretStr = SecretStr("local-development-only")
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    oidc_jwks_url: str | None = None
    oidc_algorithms: list[str] = Field(default_factory=lambda: ["RS256"])
    oidc_clock_skew_seconds: int = Field(default=30, ge=0, le=300)
    oidc_jwks_timeout_seconds: float = Field(default=5, gt=0, le=30)
    allow_self_service_organization_signup: bool = False

    database_url: str = "postgresql+asyncpg://procurex:procurex@localhost:5432/procurex"
    database_echo: bool = False
    database_pool_size: int = 10
    database_max_overflow: int = 20
    readiness_timeout_seconds: float = Field(default=3.0, ge=0.05, le=30)
    slow_request_threshold_ms: int = Field(default=1000, ge=1, le=60_000)

    cloudinary_cloud_name: str | None = None
    cloudinary_api_key: SecretStr | None = None
    cloudinary_api_secret: SecretStr | None = None
    cloudinary_folder_prefix: str = "procurex/local"
    document_max_upload_bytes: int = Field(default=25 * 1024 * 1024, gt=0)
    document_upload_intent_ttl_seconds: int = Field(default=10 * 60, ge=60, le=3600)
    document_download_ttl_seconds: int = Field(default=5 * 60, ge=60, le=900)
    document_download_timeout_seconds: float = Field(default=30, gt=0, le=120)
    document_scan_timeout_seconds: float = Field(default=60, gt=0, le=300)
    document_scanner_command: list[str] = Field(default_factory=lambda: ["clamscan"])
    document_parse_timeout_seconds: float = Field(default=120, gt=0, le=600)
    document_parser_memory_bytes: int = Field(default=768 * 1024 * 1024, ge=128 * 1024 * 1024)
    document_parser_output_bytes: int = Field(
        default=20 * 1024 * 1024, ge=1024, le=100 * 1024 * 1024
    )
    document_parser_command: list[str] = Field(
        default_factory=lambda: [sys.executable, "-m", "app.workers.document_parser"]
    )

    rabbitmq_url: SecretStr = SecretStr("amqp://procurex:procurex@localhost:5672//")
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")
    task_execution_mode: TaskExecutionMode = TaskExecutionMode.BROKER

    langgraph_checkpoint_database_url: SecretStr | None = None
    llm_provider: str = "gemini"
    llm_model: str = "gemini-3.1-pro-preview"
    gemini_api_key: SecretStr | None = None
    llm_timeout_seconds: float = Field(default=90, gt=0, le=300)
    llm_max_retries: int = Field(default=2, ge=0, le=5)
    evaluation_evidence_limit: int = Field(default=120, gt=0, le=500)
    evaluation_evidence_max_chars: int = Field(default=60_000, ge=1_000, le=500_000)

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_async_database_url(cls, value: object) -> object:
        if isinstance(value, str):
            if value.startswith("postgres://"):
                return value.replace("postgres://", "postgresql+asyncpg://", 1)
            if value.startswith("postgresql://"):
                return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        return value

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
            if not self.oidc_issuer or not self.oidc_audience or not self.oidc_jwks_url:
                raise ValueError(
                    "Staging and production require OIDC issuer, audience, and JWKS URL"
                )
            issuer = urlsplit(self.oidc_issuer)
            jwks = urlsplit(self.oidc_jwks_url)
            if issuer.scheme != "https" or issuer.hostname is None:
                raise ValueError("Staging and production require an HTTPS OIDC issuer")
            if jwks.scheme != "https" or jwks.hostname is None:
                raise ValueError("Staging and production require an HTTPS OIDC JWKS URL")
            allowed_algorithms = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
            if not self.oidc_algorithms or not set(self.oidc_algorithms) <= allowed_algorithms:
                raise ValueError(
                    "OIDC algorithms must use an allowed asymmetric signature algorithm"
                )
            if self.llm_provider != "gemini":
                raise ValueError("Staging and production require PROCUREX_LLM_PROVIDER=gemini")
            if self.gemini_api_key is None or not self.gemini_api_key.get_secret_value().strip():
                raise ValueError("Staging and production require PROCUREX_GEMINI_API_KEY")
            if self.debug:
                raise ValueError("Staging and production must disable debug mode")
            if self.database_echo:
                raise ValueError("Staging and production must disable database statement logging")
            if not self.document_scanner_command or any(
                not part.strip() for part in self.document_scanner_command
            ):
                raise ValueError("Staging and production require a document scanner command")
            if not self.document_parser_command:
                raise ValueError("Staging and production require a document parser command")
            unsafe_hosts = [
                host
                for host in self.allowed_hosts
                if not host.strip() or "*" in host or "://" in host or "/" in host
            ]
            if not self.allowed_hosts or unsafe_hosts:
                raise ValueError("Staging and production require explicit trusted hosts")
            if set(self.allowed_hosts) <= {"localhost", "127.0.0.1", "testserver"}:
                raise ValueError("Staging and production require non-local trusted hosts")
            if not self.cors_allowed_origins or "*" in self.cors_allowed_origins:
                raise ValueError("Staging and production require explicit CORS origins")
            insecure_origins = []
            for origin in self.cors_allowed_origins:
                parsed = urlsplit(origin)
                if (
                    parsed.scheme != "https"
                    or parsed.hostname is None
                    or parsed.username is not None
                    or parsed.password is not None
                    or parsed.query
                    or parsed.fragment
                    or parsed.path not in {"", "/"}
                ):
                    insecure_origins.append(origin)
            if insecure_origins:
                raise ValueError("Staging and production CORS origins must be HTTPS origins")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
