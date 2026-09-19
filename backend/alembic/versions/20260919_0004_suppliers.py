"""Create supplier onboarding and qualification tables.

Revision ID: 20260919_0004
Revises: 20260919_0003
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260919_0004"
down_revision: str | None = "20260919_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "suppliers.read": "View supplier profiles and qualification records",
    "suppliers.write": "Create and edit supplier profiles",
    "suppliers.qualify": "Assess supplier qualifications and certificates",
    "suppliers.approve": "Approve or suspend suppliers",
}


def uuid_pk() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False)


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def tenant_policy(table: str) -> None:
    tenant = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY "tenant_isolation_{table}" ON "{table}" '
            f"USING (organization_id = {tenant}) WITH CHECK (organization_id = {tenant})"
        )
    )


def upgrade() -> None:
    op.create_table(
        "suppliers",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legal_name", sa.String(250), nullable=False),
        sa.Column("trading_name", sa.String(250), nullable=True),
        sa.Column("registration_country", sa.String(2), nullable=False),
        sa.Column("registration_number", sa.String(120), nullable=False),
        sa.Column("tax_identifier", sa.String(120), nullable=True),
        sa.Column("website", sa.String(500), nullable=True),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(30), server_default="pending", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("version > 0", name=op.f("ck_suppliers_positive_version")),
        sa.CheckConstraint(
            "registration_country ~ '^[A-Z]{2}$'",
            name=op.f("ck_suppliers_registration_country_iso_code"),
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','suspended','rejected')",
            name=op.f("ck_suppliers_supplier_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_suppliers_org",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_suppliers_creator",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_suppliers"),
        sa.UniqueConstraint("organization_id", "id", name="uq_suppliers_org_id"),
        sa.UniqueConstraint(
            "organization_id",
            "registration_country",
            "registration_number",
            name="uq_suppliers_registration",
        ),
    )
    op.create_table(
        "supplier_contacts",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("title", sa.String(150), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="CASCADE",
            name="fk_supplier_contacts_supplier",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_supplier_contacts"),
        sa.UniqueConstraint(
            "organization_id", "supplier_id", "email", name="uq_supplier_contacts_email"
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_supplier_contacts_org_id"),
    )
    op.create_table(
        "supplier_qualifications",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("status", sa.String(30), server_default="pending", nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("assessment_notes", sa.Text(), nullable=True),
        sa.Column("assessed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assessed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name=op.f("ck_supplier_qualifications_valid_period"),
        ),
        sa.CheckConstraint(
            "status IN ('pending','qualified','unqualified','expired')",
            name=op.f("ck_supplier_qualifications_supplier_qualification_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="CASCADE",
            name="fk_supplier_qualifications_supplier",
        ),
        sa.ForeignKeyConstraint(
            ["assessed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_supplier_qualifications_assessor",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_supplier_qualifications"),
        sa.UniqueConstraint(
            "organization_id", "supplier_id", "category", name="uq_supplier_qualifications_category"
        ),
        sa.UniqueConstraint(
            "organization_id", "supplier_id", "id", name="uq_supplier_qualifications_parent_id"
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_supplier_qualifications_org_id"),
    )
    op.create_table(
        "supplier_certificates",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("qualification_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("certificate_type", sa.String(120), nullable=False),
        sa.Column("certificate_number", sa.String(150), nullable=False),
        sa.Column("issuer", sa.String(250), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(30), server_default="pending", nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "expires_on IS NULL OR issued_on IS NULL OR expires_on >= issued_on",
            name=op.f("ck_supplier_certificates_valid_period"),
        ),
        sa.CheckConstraint(
            "status IN ('pending','verified','rejected','expired')",
            name=op.f("ck_supplier_certificates_supplier_certificate_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="CASCADE",
            name="fk_supplier_certificates_supplier",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "supplier_id", "qualification_id"],
            [
                "supplier_qualifications.organization_id",
                "supplier_qualifications.supplier_id",
                "supplier_qualifications.id",
            ],
            ondelete="RESTRICT",
            name="fk_supplier_certificates_qualification",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            ondelete="RESTRICT",
            name="fk_supplier_certificates_document_version",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_supplier_certificates_reviewer",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_supplier_certificates"),
        sa.UniqueConstraint(
            "organization_id",
            "supplier_id",
            "certificate_type",
            "certificate_number",
            name="uq_supplier_certificates_identity",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_supplier_certificates_org_id"),
    )

    for table in (
        "suppliers",
        "supplier_contacts",
        "supplier_qualifications",
        "supplier_certificates",
    ):
        tenant_policy(table)

    permission_rows = ",".join(
        f"('{code}', '{description}')" for code, description in PERMISSIONS.items()
    )
    permission_codes = ",".join(f"'{code}'" for code in PERMISSIONS)
    op.execute(
        sa.text(
            "INSERT INTO permissions (code, description) VALUES "
            f"{permission_rows} ON CONFLICT (code) DO NOTHING"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO role_permissions (organization_id, role_id, permission_code) "
            "SELECT roles.organization_id, roles.id, permissions.code "
            "FROM roles CROSS JOIN permissions "
            "WHERE roles.is_system IS TRUE "
            "AND roles.name = 'Organization administrator' "
            f"AND permissions.code IN ({permission_codes}) "
            "ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    permission_codes = ",".join(f"'{code}'" for code in PERMISSIONS)
    op.execute(
        sa.text(f"DELETE FROM role_permissions WHERE permission_code IN ({permission_codes})")
    )
    op.execute(sa.text(f"DELETE FROM permissions WHERE code IN ({permission_codes})"))
    for table in (
        "supplier_certificates",
        "supplier_qualifications",
        "supplier_contacts",
        "suppliers",
    ):
        op.drop_table(table)
