from sqlalchemy import Enum

from app import models  # noqa: F401
from app.db.base import Base

EXPECTED_TABLES = {
    "organizations",
    "users",
    "memberships",
    "roles",
    "permissions",
    "role_permissions",
    "membership_roles",
    "organization_settings",
    "documents",
    "document_versions",
    "cloudinary_assets",
    "document_scans",
    "analysis_runs",
    "model_invocations",
    "jobs",
    "outbox_events",
    "audit_events",
    "requisitions",
    "requisition_lines",
    "requisition_requirements",
    "requisition_revisions",
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
