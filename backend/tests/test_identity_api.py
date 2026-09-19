from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import app
from app.schemas.identity import OrganizationBootstrapRequest, OrganizationSettingsWrite
from app.services.identity import BootstrapDeniedError, verify_bootstrap_key


def test_identity_routes_are_in_openapi() -> None:
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    assert "/api/v1/organizations/dev-bootstrap" in schema["paths"]
    assert "/api/v1/organizations/current" in schema["paths"]
    assert "/api/v1/organizations/current/settings" in schema["paths"]


def test_bootstrap_schema_normalizes_names() -> None:
    payload = OrganizationBootstrapRequest(
        organization_name="  Acme Limited  ",
        organization_slug="acme-limited",
        admin_email="ADMIN@EXAMPLE.COM",
        admin_display_name="  Admin User ",
    )
    assert payload.organization_name == "Acme Limited"
    assert payload.admin_display_name == "Admin User"


def test_bootstrap_key_uses_configured_secret() -> None:
    settings = Settings(dev_bootstrap_key="expected", _env_file=None)
    verify_bootstrap_key(settings, "expected")
    with pytest.raises(BootstrapDeniedError):
        verify_bootstrap_key(settings, "wrong")


def test_settings_effective_time_requires_timezone() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        OrganizationSettingsWrite(
            settings={"currency": "PKR"}, effective_from=datetime(2026, 9, 19, 10, 0)
        )
