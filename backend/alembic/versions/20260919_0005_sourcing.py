"""Create RFQ, invitation, quotation, and clarification tables.

Revision ID: 20260919_0005
Revises: 20260919_0004
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260919_0005"
down_revision: str | None = "20260919_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "sourcing.read": "View RFQs, invitations, submissions, and clarifications",
    "sourcing.write": "Create and edit draft RFQs",
    "sourcing.invite": "Select approved suppliers for RFQs",
    "sourcing.publish": "Publish, amend, close, or cancel RFQs",
    "sourcing.submissions.manage": "Record supplier quotation submissions",
    "sourcing.clarifications.write": "Create and answer RFQ clarifications",
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
        "rfqs",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requisition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("submission_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("terms", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(30), server_default="draft", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("publication_number", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("version > 0", name=op.f("ck_rfqs_positive_version")),
        sa.CheckConstraint(
            "publication_number >= 0", name=op.f("ck_rfqs_nonnegative_publication_number")
        ),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_rfqs_currency_iso_code")),
        sa.CheckConstraint(
            "status IN ('draft','published','closed','cancelled')",
            name=op.f("ck_rfqs_rfq_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_rfqs_org"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requisition_id"],
            ["requisitions.organization_id", "requisitions.id"],
            ondelete="RESTRICT",
            name="fk_rfqs_requisition",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_rfqs_creator",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rfqs"),
        sa.UniqueConstraint("organization_id", "id", name="uq_rfqs_org_id"),
        sa.UniqueConstraint("organization_id", "requisition_id", name="uq_rfqs_requisition"),
    )
    op.create_table(
        "rfq_items",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requisition_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("category", sa.String(120), nullable=True),
        sa.Column("specifications", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("alternatives_allowed", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.CheckConstraint("line_number > 0", name=op.f("ck_rfq_items_positive_line_number")),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_rfq_items_positive_quantity")),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id"],
            ["rfqs.organization_id", "rfqs.id"],
            ondelete="CASCADE",
            name="fk_rfq_items_rfq",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requisition_line_id"],
            ["requisition_lines.organization_id", "requisition_lines.id"],
            ondelete="RESTRICT",
            name="fk_rfq_items_requisition_line",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rfq_items"),
        sa.UniqueConstraint(
            "organization_id", "rfq_id", "line_number", name="uq_rfq_items_line_number"
        ),
        sa.UniqueConstraint("organization_id", "rfq_id", "id", name="uq_rfq_items_parent_id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_rfq_items_org_id"),
    )
    op.create_table(
        "rfq_requirements",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requisition_requirement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("priority", sa.String(30), nullable=False),
        sa.Column("criterion", sa.Text(), nullable=False),
        sa.Column("verification_method", sa.String(500), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "priority IN ('mandatory','preferred')",
            name=op.f("ck_rfq_requirements_priority"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id"],
            ["rfqs.organization_id", "rfqs.id"],
            ondelete="CASCADE",
            name="fk_rfq_requirements_rfq",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "item_id"],
            ["rfq_items.organization_id", "rfq_items.rfq_id", "rfq_items.id"],
            ondelete="CASCADE",
            name="fk_rfq_requirements_item",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requisition_requirement_id"],
            ["requisition_requirements.organization_id", "requisition_requirements.id"],
            ondelete="RESTRICT",
            name="fk_rfq_requirements_requisition_requirement",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rfq_requirements"),
        sa.UniqueConstraint("organization_id", "id", name="uq_rfq_requirements_org_id"),
    )
    op.create_table(
        "rfq_revisions",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("publication_number", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "publication_number > 0", name=op.f("ck_rfq_revisions_positive_publication_number")
        ),
        sa.CheckConstraint(
            "length(content_digest) = 64", name=op.f("ck_rfq_revisions_content_digest_length")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id"],
            ["rfqs.organization_id", "rfqs.id"],
            ondelete="CASCADE",
            name="fk_rfq_revisions_rfq",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_rfq_revisions_creator",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rfq_revisions"),
        sa.UniqueConstraint(
            "organization_id",
            "rfq_id",
            "publication_number",
            name="uq_rfq_revisions_publication",
        ),
        sa.UniqueConstraint("organization_id", "rfq_id", "id", name="uq_rfq_revisions_parent_id"),
    )
    op.create_table(
        "rfq_invitations",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(30), server_default="invited", nullable=False),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('invited','acknowledged','submitted','no_bid','revoked')",
            name=op.f("ck_rfq_invitations_rfq_invitation_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id"],
            ["rfqs.organization_id", "rfqs.id"],
            ondelete="CASCADE",
            name="fk_rfq_invitations_rfq",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="RESTRICT",
            name="fk_rfq_invitations_supplier",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "rfq_revision_id"],
            ["rfq_revisions.organization_id", "rfq_revisions.rfq_id", "rfq_revisions.id"],
            ondelete="RESTRICT",
            name="fk_rfq_invitations_revision",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rfq_invitations"),
        sa.UniqueConstraint(
            "organization_id", "rfq_id", "supplier_id", name="uq_rfq_invitations_supplier"
        ),
        sa.UniqueConstraint("organization_id", "rfq_id", "id", name="uq_rfq_invitations_parent_id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_rfq_invitations_org_id"),
    )
    op.create_table(
        "quote_submissions",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invitation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("delivery_terms", sa.Text(), nullable=False),
        sa.Column("payment_terms", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), server_default="submitted", nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("submitted_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("version > 0", name=op.f("ck_quote_submissions_positive_version")),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name=op.f("ck_quote_submissions_currency_iso_code")
        ),
        sa.CheckConstraint(
            "length(content_digest) = 64",
            name=op.f("ck_quote_submissions_content_digest_length"),
        ),
        sa.CheckConstraint(
            "status IN ('submitted','superseded','withdrawn')",
            name=op.f("ck_quote_submissions_quote_submission_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "invitation_id"],
            [
                "rfq_invitations.organization_id",
                "rfq_invitations.rfq_id",
                "rfq_invitations.id",
            ],
            ondelete="RESTRICT",
            name="fk_quote_submissions_invitation",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="RESTRICT",
            name="fk_quote_submissions_supplier",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "rfq_revision_id"],
            ["rfq_revisions.organization_id", "rfq_revisions.rfq_id", "rfq_revisions.id"],
            ondelete="RESTRICT",
            name="fk_quote_submissions_revision",
        ),
        sa.ForeignKeyConstraint(
            ["submitted_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_quote_submissions_submitter",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quote_submissions"),
        sa.UniqueConstraint(
            "organization_id", "invitation_id", "version", name="uq_quote_submissions_version"
        ),
        sa.UniqueConstraint(
            "organization_id", "rfq_id", "id", name="uq_quote_submissions_parent_id"
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_quote_submissions_org_id"),
    )
    op.create_table(
        "quote_lines",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("tax_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("freight_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("is_alternative", sa.Boolean(), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.CheckConstraint("quantity > 0", name=op.f("ck_quote_lines_positive_quantity")),
        sa.CheckConstraint("unit_price >= 0", name=op.f("ck_quote_lines_nonnegative_unit_price")),
        sa.CheckConstraint("tax_amount >= 0", name=op.f("ck_quote_lines_nonnegative_tax_amount")),
        sa.CheckConstraint(
            "freight_amount >= 0", name=op.f("ck_quote_lines_nonnegative_freight_amount")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "submission_id"],
            [
                "quote_submissions.organization_id",
                "quote_submissions.rfq_id",
                "quote_submissions.id",
            ],
            ondelete="CASCADE",
            name="fk_quote_lines_submission",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "rfq_item_id"],
            ["rfq_items.organization_id", "rfq_items.rfq_id", "rfq_items.id"],
            ondelete="RESTRICT",
            name="fk_quote_lines_rfq_item",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quote_lines"),
        sa.UniqueConstraint(
            "organization_id",
            "submission_id",
            "rfq_item_id",
            name="uq_quote_lines_submission_item",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_quote_lines_org_id"),
    )
    op.create_table(
        "rfq_clarifications",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invitation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("visibility", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), server_default="open", nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("asked_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("answered_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "visibility IN ('shared','private')",
            name=op.f("ck_rfq_clarifications_clarification_visibility"),
        ),
        sa.CheckConstraint(
            "status IN ('open','answered')",
            name=op.f("ck_rfq_clarifications_clarification_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id"],
            ["rfqs.organization_id", "rfqs.id"],
            ondelete="CASCADE",
            name="fk_rfq_clarifications_rfq",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "invitation_id"],
            [
                "rfq_invitations.organization_id",
                "rfq_invitations.rfq_id",
                "rfq_invitations.id",
            ],
            ondelete="RESTRICT",
            name="fk_rfq_clarifications_invitation",
        ),
        sa.ForeignKeyConstraint(
            ["asked_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_rfq_clarifications_asker",
        ),
        sa.ForeignKeyConstraint(
            ["answered_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_rfq_clarifications_answerer",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rfq_clarifications"),
        sa.UniqueConstraint("organization_id", "id", name="uq_rfq_clarifications_org_id"),
    )

    for table in (
        "rfqs",
        "rfq_items",
        "rfq_requirements",
        "rfq_revisions",
        "rfq_invitations",
        "quote_submissions",
        "quote_lines",
        "rfq_clarifications",
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
        "rfq_clarifications",
        "quote_lines",
        "quote_submissions",
        "rfq_invitations",
        "rfq_revisions",
        "rfq_requirements",
        "rfq_items",
        "rfqs",
    ):
        op.drop_table(table)
