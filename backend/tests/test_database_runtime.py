from sqlalchemy.pool import NullPool

from app.core.config import Settings, TaskExecutionMode
from app.core.database import build_engine


async def test_eager_tasks_use_loop_safe_unpooled_database_connections() -> None:
    engine = build_engine(
        Settings(task_execution_mode=TaskExecutionMode.EAGER, _env_file=None)
    )
    try:
        assert isinstance(engine.sync_engine.pool, NullPool)
    finally:
        await engine.dispose()


async def test_broker_workers_keep_the_configured_connection_pool() -> None:
    engine = build_engine(
        Settings(task_execution_mode=TaskExecutionMode.BROKER, _env_file=None)
    )
    try:
        assert not isinstance(engine.sync_engine.pool, NullPool)
    finally:
        await engine.dispose()
