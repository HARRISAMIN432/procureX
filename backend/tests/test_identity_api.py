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
    assert "/api/v1/requisitions" in schema["paths"]
    assert "/api/v1/requisitions/{requisition_id}/submit" in schema["paths"]
    assert "/api/v1/budgets" in schema["paths"]
    assert "/api/v1/approval-policies" in schema["paths"]
    assert "/api/v1/requisitions/{requisition_id}/approval-requests" in schema["paths"]
    assert "/api/v1/approval-requests/{approval_request_id}/approve" in schema["paths"]
    assert "/api/v1/suppliers" in schema["paths"]
    assert (
        "/api/v1/suppliers/{supplier_id}/qualifications/{qualification_id}/decision"
        in schema["paths"]
    )
    assert "/api/v1/suppliers/{supplier_id}/approve" in schema["paths"]
    assert "/api/v1/rfqs" in schema["paths"]
    assert "/api/v1/rfqs/{rfq_id}/publish" in schema["paths"]
    assert "/api/v1/rfqs/{rfq_id}/amend" in schema["paths"]
    assert "/api/v1/rfq-invitations/{invitation_id}/submissions" in schema["paths"]
    assert "/api/v1/quote-submissions/{submission_id}/withdraw" in schema["paths"]
    assert "/api/v1/rfqs/{rfq_id}/clarifications/{clarification_id}/answer" in schema["paths"]
    assert "/api/v1/documents/upload-intents" in schema["paths"]
    assert (
        "/api/v1/documents/{document_id}/versions/{version_id}/complete-upload"
        in schema["paths"]
    )
    assert "/api/v1/documents/versions/{version_id}/scan-results" in schema["paths"]
    assert "/api/v1/documents/versions/{version_id}/parse-results" in schema["paths"]
    assert "/api/v1/documents/versions/{version_id}/download" in schema["paths"]
    assert "/api/v1/document-versions/{version_id}/extractions" in schema["paths"]
    assert (
        "/api/v1/extractions/{extraction_id}/fields/{field_id}/review" in schema["paths"]
    )
    assert "/api/v1/extractions/{extraction_id}/finalize" in schema["paths"]
    assert "/api/v1/rfqs/{rfq_id}/evaluations" in schema["paths"]
    assert "/api/v1/evaluations/{evaluation_id}" in schema["paths"]


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
