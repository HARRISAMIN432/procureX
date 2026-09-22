from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import AuthMode, Settings
from app.main import app, create_app
from app.schemas.identity import (
    MemberInviteCreate,
    MembershipUpdate,
    OrganizationBootstrapRequest,
    OrganizationSettingsWrite,
    RoleCreate,
)
from app.services.identity import PERMISSION_CATALOG, BootstrapDeniedError, verify_bootstrap_key


def test_identity_routes_are_in_openapi() -> None:
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    assert "/api/v1/organizations/dev-bootstrap" in schema["paths"]
    assert "/api/v1/organizations/mine" in schema["paths"]
    assert "/api/v1/organizations/current" in schema["paths"]
    assert "/api/v1/organizations/current/settings" in schema["paths"]
    assert "/api/v1/organizations/current/members" in schema["paths"]
    assert "/api/v1/organizations/current/members/{membership_id}" in schema["paths"]
    assert "/api/v1/organizations/current/roles" in schema["paths"]
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
        "/api/v1/documents/{document_id}/versions/{version_id}/complete-upload" in schema["paths"]
    )
    assert "/api/v1/documents/versions/{version_id}/scan-results" not in schema["paths"]
    assert "/api/v1/documents/versions/{version_id}/parse-results" not in schema["paths"]
    assert "/api/v1/documents/versions/{version_id}/download" in schema["paths"]
    assert "/api/v1/document-versions/{version_id}/extractions" not in schema["paths"]
    assert "/api/v1/extractions/{extraction_id}/fields/{field_id}/review" in schema["paths"]
    assert "/api/v1/extractions/{extraction_id}/finalize" in schema["paths"]
    assert "/api/v1/rfqs/{rfq_id}/evaluations" in schema["paths"]
    assert "/api/v1/evaluations/{evaluation_id}" in schema["paths"]
    assert "/api/v1/awards/{award_id}/purchase-orders" in schema["paths"]
    assert "/api/v1/purchase-orders/{purchase_order_id}/issue" in schema["paths"]
    assert "/api/v1/purchase-orders/{purchase_order_id}/receipts" in schema["paths"]
    assert "/api/v1/purchase-orders/{purchase_order_id}/invoices" in schema["paths"]
    assert "/api/v1/invoices/{invoice_id}/match" in schema["paths"]
    assert "/api/v1/invoices/{invoice_id}/accounting-exports" in schema["paths"]


def test_workspace_discovery_is_not_exposed_in_development_header_mode() -> None:
    local_app = create_app(Settings(auth_mode=AuthMode.DEV_HEADERS, _env_file=None))

    with TestClient(local_app) as client:
        response = client.get("/api/v1/organizations/mine")

    assert response.status_code == 404


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


def test_bootstrap_catalog_includes_order_operations_permissions() -> None:
    assert {
        "orders.read",
        "orders.write",
        "orders.approve",
        "orders.issue",
        "orders.acknowledge",
        "orders.receive",
        "invoices.read",
        "invoices.write",
        "invoices.match",
        "invoices.approve",
        "accounting.export",
        "accounting.reconcile",
    } <= PERMISSION_CATALOG.keys()


def test_settings_effective_time_requires_timezone() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        OrganizationSettingsWrite(
            settings={"currency": "PKR"}, effective_from=datetime(2026, 9, 19, 10, 0)
        )


def test_multi_user_schemas_reject_duplicate_assignments_and_empty_updates() -> None:
    role_id = "11111111-1111-1111-1111-111111111111"
    with pytest.raises(ValidationError, match="unique"):
        RoleCreate(name="Buyer", permission_codes=["orders.read", "orders.read"])
    with pytest.raises(ValidationError, match="unique"):
        MemberInviteCreate(
            email="buyer@example.com",
            display_name="Buyer",
            role_ids=[role_id, role_id],
        )
    with pytest.raises(ValidationError, match="change"):
        MembershipUpdate()
