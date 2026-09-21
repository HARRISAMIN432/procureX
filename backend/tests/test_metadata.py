from sqlalchemy import Enum

from app import models  # noqa: F401
from app.db.base import Base

EXPECTED_TABLES = {
    "after_sales_cases",
    "accounting_exports",
    "accounting_sandbox_entries",
    "allocation_scenarios",
    "allocation_lines",
    "organizations",
    "users",
    "memberships",
    "roles",
    "permissions",
    "role_permissions",
    "membership_roles",
    "organization_settings",
    "organization_subscriptions",
    "organization_closure_requests",
    "data_export_requests",
    "support_cases",
    "documents",
    "document_versions",
    "delivery_receipts",
    "delivery_receipt_lines",
    "cloudinary_assets",
    "document_scans",
    "document_parses",
    "document_pages",
    "extractions",
    "extracted_fields",
    "evidence_anchors",
    "field_reviews",
    "evaluations",
    "offer_evaluations",
    "requirement_checks",
    "requirement_check_evidence",
    "analysis_runs",
    "model_invocations",
    "jobs",
    "invoices",
    "invoice_lines",
    "invoice_matches",
    "match_exceptions",
    "outbox_events",
    "audit_events",
    "requisitions",
    "requisition_lines",
    "requisition_requirements",
    "requisition_revisions",
    "budgets",
    "budget_ledger_entries",
    "budget_reservations",
    "approval_policies",
    "approval_requests",
    "approval_decisions",
    "awards",
    "award_decisions",
    "suppliers",
    "supplier_contacts",
    "supplier_qualifications",
    "supplier_certificates",
    "rfqs",
    "rfq_items",
    "rfq_requirements",
    "rfq_revisions",
    "rfq_invitations",
    "quote_submissions",
    "quote_submission_documents",
    "quote_lines",
    "rfq_clarifications",
    "purchase_orders",
    "purchase_order_versions",
    "purchase_order_lines",
    "receipt_returns",
}


def test_foundation_tables_are_registered() -> None:
    assert EXPECTED_TABLES == set(Base.metadata.tables)


def test_tenant_tables_have_organization_id() -> None:
    global_tables = {"organizations", "users", "permissions"}
    for table_name, table in Base.metadata.tables.items():
        if table_name not in global_tables:
            assert "organization_id" in table.columns, table_name


def test_enum_values_use_wire_values() -> None:
    status_type = Base.metadata.tables["organizations"].c.status.type
    assert isinstance(status_type, Enum)
    assert status_type.enums == ["active", "suspended", "closing", "closed"]
    document_version_status = Base.metadata.tables["document_versions"].c.status.type
    assert isinstance(document_version_status, Enum)
    assert "parsed" in document_version_status.enums
