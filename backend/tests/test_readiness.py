import asyncio

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


async def successful_probe() -> None:
    return None


async def failed_probe() -> None:
    raise RuntimeError("postgresql://user:secret@database/procurex")


async def stalled_probe() -> None:
    await asyncio.Event().wait()


def test_readiness_reports_database_success() -> None:
    application = create_app(Settings(_env_file=None), readiness_probe=successful_probe)
    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": {"status": "ok"}},
    }


def test_readiness_fails_closed_without_exposing_dependency_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    application = create_app(Settings(_env_file=None), readiness_probe=failed_probe)
    with TestClient(application) as client:
        response = client.get("/health/ready", headers={"X-Request-ID": "database-drill-1"})

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": {"status": "unavailable"}},
    }
    assert "secret" not in response.text
    assert "secret" not in caplog.text
    assert response.headers["x-request-id"] == "database-drill-1"


def test_readiness_times_out_and_liveness_remains_available() -> None:
    application = create_app(
        Settings(readiness_timeout_seconds=0.05, _env_file=None),
        readiness_probe=stalled_probe,
    )
    with TestClient(application) as client:
        readiness = client.get("/health/ready")
        liveness = client.get("/health/live")

    assert readiness.status_code == 503
    assert readiness.json()["checks"]["database"]["status"] == "timeout"
    assert liveness.status_code == 200
    assert liveness.json() == {"status": "ok"}
