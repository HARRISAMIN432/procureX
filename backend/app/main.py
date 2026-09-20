import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import Environment, Settings, get_settings
from app.core.database import SessionFactory, close_database
from app.core.http_security import SecurityHeadersMiddleware

logger = logging.getLogger(__name__)
ReadinessProbe = Callable[[], Awaitable[None]]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_database()


async def database_readiness_probe() -> None:
    async with SessionFactory() as session:
        await session.execute(text("SELECT 1"))


def create_app(
    settings: Settings | None = None, *, readiness_probe: ReadinessProbe | None = None
) -> FastAPI:
    configured = settings or get_settings()
    probe = readiness_probe or database_readiness_probe
    production = configured.environment is Environment.PRODUCTION
    application = FastAPI(
        title=configured.app_name,
        debug=configured.debug,
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if production else "/docs",
        redoc_url=None if production else "/redoc",
        openapi_url=None if production else "/openapi.json",
    )
    application.include_router(api_router, prefix=configured.api_v1_prefix)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=configured.allowed_hosts)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configured.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Request-ID",
            "X-Organization-ID",
            "X-User-ID",
            "X-Dev-Bootstrap-Key",
        ],
    )
    application.add_middleware(
        SecurityHeadersMiddleware,
        enable_hsts=configured.environment in {Environment.STAGING, Environment.PRODUCTION},
        slow_request_threshold_ms=configured.slow_request_threshold_ms,
    )

    @application.get("/health/live", tags=["health"])
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @application.get(
        "/health/ready",
        tags=["health"],
        response_model=None,
        responses={503: {"description": "A required dependency is unavailable"}},
    )
    async def readiness() -> dict[str, Any] | JSONResponse:
        try:
            async with asyncio.timeout(configured.readiness_timeout_seconds):
                await probe()
        except TimeoutError:
            logger.warning("readiness probe timed out", extra={"dependency": "database"})
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "checks": {"database": {"status": "timeout"}},
                },
            )
        except Exception as exc:
            logger.warning(
                "readiness probe failed",
                extra={"dependency": "database", "error_type": type(exc).__name__},
            )
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "checks": {"database": {"status": "unavailable"}},
                },
            )
        return {"status": "ok", "checks": {"database": {"status": "ok"}}}

    return application


app = create_app()
