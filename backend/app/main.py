from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from sqlalchemy import text
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_router
from app.core.config import Environment, Settings, get_settings
from app.core.database import SessionFactory, close_database
from app.core.http_security import SecurityHeadersMiddleware


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_database()


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or get_settings()
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
    )

    @application.get("/health/live", tags=["health"])
    async def liveness() -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/health/ready", tags=["health"])
    async def readiness() -> dict[str, Any]:
        async with SessionFactory() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}

    return application


app = create_app()
