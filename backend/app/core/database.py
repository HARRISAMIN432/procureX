from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import Settings, TaskExecutionMode, get_settings


def build_engine(settings: Settings) -> AsyncEngine:
    options: dict[str, object] = {
        "echo": settings.database_echo,
        "pool_pre_ping": True,
    }
    if settings.task_execution_mode is TaskExecutionMode.EAGER:
        # Eager Celery tasks execute in Starlette's thread pool and create their own event loop.
        # Async database connections are loop-bound, so they must not be shared with the API loop.
        options["poolclass"] = NullPool
    else:
        options["pool_size"] = settings.database_pool_size
        options["max_overflow"] = settings.database_max_overflow
    return create_async_engine(settings.database_url, **options)


settings = get_settings()
engine = build_engine(settings)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


@asynccontextmanager
async def tenant_transaction(organization_id: UUID) -> AsyncIterator[AsyncSession]:
    """Open a transaction with the PostgreSQL RLS tenant context set locally."""
    async with SessionFactory() as session, session.begin():
        await session.execute(
            text("SELECT set_config('app.current_organization_id', :organization_id, true)"),
            {"organization_id": str(organization_id)},
        )
        yield session


async def close_database() -> None:
    await engine.dispose()
