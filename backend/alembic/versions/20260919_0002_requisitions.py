"""Create requisition workflow tables and permissions.

Revision ID: 20260919_0002
Revises: 20260919_0001
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260919_0002"
down_revision: str | None = "20260919_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "requisitions.read": "View requisitions in the organization",
    "requisitions.write": "Create and edit draft requisitions",
    "requisitions.submit": "Submit requisitions for approval",
    "requisitions.cancel": "Cancel permitted requisitions",
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
        "requisitions",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("department", sa.String(150), nullable=True),
        sa.Column("cost_center", sa.String(100), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("need_by_date", sa.Date(), nullable=True),
        sa.Column("delivery_location", sa.String(500), nullable=True),
        sa.Column("status", sa.String(30), server_default="draft", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("version > 0", name=op.f("ck_requisitions_positive_version")),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name=op.f("ck_requisitions_currency_iso_code")
        ),
        sa.CheckConstraint(
            "status IN ('draft','submitted','changes_requested','approved','rejected',"
            "'cancelled','sourcing','ordered','closed')",
            name=op.f("ck_requisitions_requisition_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_requisitions_org",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_requisitions_creator",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_requisitions"),
        sa.UniqueConstraint("organization_id", "id", name="uq_requisitions_org_id"),
    )
    op.create_table(
        "requisition_lines",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requisition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("estimated_unit_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("category", sa.String(120), nullable=True),
        sa.Column("specifications", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("alternatives_allowed", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "line_number > 0", name=op.f("ck_requisition_lines_positive_line_number")
        ),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_requisition_lines_positive_quantity")),
        sa.CheckConstraint(
            "estimated_unit_price IS NULL OR estimated_unit_price >= 0",
            name=op.f("ck_requisition_lines_nonnegative_estimated_unit_price"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requisition_id"],
            ["requisitions.organization_id", "requisitions.id"],
            ondelete="CASCADE",
            name="fk_requisition_lines_requisition",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_requisition_lines"),
        sa.UniqueConstraint(
            "organization_id",
            "requisition_id",
            "line_number",
            name="uq_requisition_lines_line_number",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_requisition_lines_org_id"),
        sa.UniqueConstraint(
            "organization_id", "requisition_id", "id", name="uq_requisition_lines_parent_id"
        ),
    )
    op.create_table(
        "requisition_requirements",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requisition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority", sa.String(30), nullable=False),
        sa.Column("criterion", sa.Text(), nullable=False),
        sa.Column("verification_method", sa.String(500), nullable=False),
        sa.Column("source", sa.String(30), server_default="human", nullable=False),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "priority IN ('mandatory','preferred')",
            name=op.f("ck_requisition_requirements_requirement_priority"),
        ),
        sa.CheckConstraint(
            "source IN ('human','ai_assisted')",
            name=op.f("ck_requisition_requirements_requirement_source"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requisition_id"],
            ["requisitions.organization_id", "requisitions.id"],
            ondelete="CASCADE",
            name="fk_requisition_requirements_requisition",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requisition_id", "line_id"],
            [
                "requisition_lines.organization_id",
                "requisition_lines.requisition_id",
                "requisition_lines.id",
            ],
            ondelete="CASCADE",
            name="fk_requisition_requirements_line",
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_requisition_requirements_confirmer",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_requisition_requirements"),
        sa.UniqueConstraint("organization_id", "id", name="uq_requisition_requirements_org_id"),
    )
    op.create_table(
        "requisition_revisions",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requisition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_requisition_revisions_positive_version")),
        sa.CheckConstraint(
            "length(content_digest) = 64",
            name=op.f("ck_requisition_revisions_content_digest_length"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requisition_id"],
            ["requisitions.organization_id", "requisitions.id"],
            ondelete="CASCADE",
            name="fk_requisition_revisions_requisition",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_requisition_revisions_creator",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_requisition_revisions"),
        sa.UniqueConstraint(
            "organization_id",
            "requisition_id",
            "version",
            name="uq_requisition_revisions_version",
        ),
    )

    for table in (
        "requisitions",
        "requisition_lines",
        "requisition_requirements",
        "requisition_revisions",
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
        "requisition_revisions",
        "requisition_requirements",
        "requisition_lines",
        "requisitions",
    ):
        op.drop_table(table)
