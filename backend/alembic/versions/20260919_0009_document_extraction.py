"""Add structured extraction, evidence, and field review records.

Revision ID: 20260919_0009
Revises: 20260919_0008
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260919_0009"
down_revision: str | None = "20260919_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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
    op.create_unique_constraint(
        "uq_document_pages_parent_id",
        "document_pages",
        ["organization_id", "document_version_id", "parse_id", "id"],
    )
    op.create_table(
        "extractions",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("result_key", sa.String(200), nullable=False),
        sa.Column("schema_name", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("version > 0", name=op.f("ck_extractions_positive_version")),
        sa.CheckConstraint("revision > 0", name=op.f("ck_extractions_positive_revision")),
        sa.CheckConstraint(
            "length(content_digest) = 64", name=op.f("ck_extractions_content_digest_length")
        ),
        sa.CheckConstraint(
            "length(source_digest) = 64", name=op.f("ck_extractions_source_digest_length")
        ),
        sa.CheckConstraint(
            "status IN ('awaiting_review','in_review','completed')",
            name=op.f("ck_extractions_extraction_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id", "parse_id"],
            [
                "document_parses.organization_id",
                "document_parses.document_version_id",
                "document_parses.id",
            ],
            ondelete="RESTRICT",
            name="fk_extractions_parse",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "analysis_run_id"],
            ["analysis_runs.organization_id", "analysis_runs.id"],
            ondelete="RESTRICT",
            name="fk_extractions_analysis_run",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_extractions"),
        sa.UniqueConstraint(
            "organization_id",
            "document_version_id",
            "version",
            name="uq_extractions_version",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "document_version_id",
            "result_key",
            name="uq_extractions_result_key",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "document_version_id",
            "id",
            name="uq_extractions_parent_id",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_extractions_org_id"),
    )
    op.create_table(
        "extracted_fields",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("extraction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_key", sa.String(160), nullable=False),
        sa.Column("label", sa.String(250), nullable=False),
        sa.Column("data_type", sa.String(50), nullable=False),
        sa.Column("raw_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("normalized_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("is_critical", sa.Boolean(), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_extracted_fields_valid_confidence"),
        ),
        sa.CheckConstraint(
            "status <> 'missing' OR (raw_value IS NULL AND normalized_value IS NULL)",
            name=op.f("ck_extracted_fields_missing_has_no_value"),
        ),
        sa.CheckConstraint(
            "status IN ('proposed','missing','ambiguous','conflicting','verified','rejected')",
            name=op.f("ck_extracted_fields_extracted_field_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id", "extraction_id"],
            [
                "extractions.organization_id",
                "extractions.document_version_id",
                "extractions.id",
            ],
            ondelete="CASCADE",
            name="fk_extracted_fields_extraction",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_extracted_fields"),
        sa.UniqueConstraint(
            "organization_id", "extraction_id", "field_key", name="uq_extracted_fields_key"
        ),
        sa.UniqueConstraint(
            "organization_id", "extraction_id", "id", name="uq_extracted_fields_parent_id"
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_extracted_fields_org_id"),
    )
    op.create_table(
        "evidence_anchors",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("extraction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quoted_text", sa.Text(), nullable=True),
        sa.Column("bounding_box", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cell_range", sa.String(100), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id", "extraction_id", "field_id"],
            [
                "extracted_fields.organization_id",
                "extracted_fields.extraction_id",
                "extracted_fields.id",
            ],
            ondelete="CASCADE",
            name="fk_evidence_anchors_field",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id", "parse_id", "page_id"],
            [
                "document_pages.organization_id",
                "document_pages.document_version_id",
                "document_pages.parse_id",
                "document_pages.id",
            ],
            ondelete="RESTRICT",
            name="fk_evidence_anchors_page",
        ),
        sa.CheckConstraint(
            "quoted_text IS NOT NULL OR bounding_box IS NOT NULL OR cell_range IS NOT NULL",
            name=op.f("ck_evidence_anchors_has_locator"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evidence_anchors"),
        sa.UniqueConstraint("organization_id", "id", name="uq_evidence_anchors_org_id"),
    )
    op.create_table(
        "field_reviews",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("extraction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("previous_status", sa.String(30), nullable=False),
        sa.Column("previous_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reviewed_status", sa.String(30), nullable=False),
        sa.Column("reviewed_value", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('verify','correct','reject')",
            name=op.f("ck_field_reviews_field_review_action"),
        ),
        sa.CheckConstraint(
            "previous_status IN "
            "('proposed','missing','ambiguous','conflicting','verified','rejected')",
            name=op.f("ck_field_reviews_valid_previous_status"),
        ),
        sa.CheckConstraint(
            "reviewed_status IN ('verified','rejected')",
            name=op.f("ck_field_reviews_valid_reviewed_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "extraction_id", "field_id"],
            [
                "extracted_fields.organization_id",
                "extracted_fields.extraction_id",
                "extracted_fields.id",
            ],
            ondelete="RESTRICT",
            name="fk_field_reviews_field",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_field_reviews_reviewer",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_field_reviews"),
        sa.UniqueConstraint("organization_id", "id", name="uq_field_reviews_org_id"),
    )
    for table in ("extractions", "extracted_fields", "evidence_anchors", "field_reviews"):
        tenant_policy(table)
    op.execute(
        sa.text(
            "INSERT INTO permissions (code, description) VALUES "
            "('documents.review', 'Review and finalize extracted document fields') "
            "ON CONFLICT (code) DO NOTHING"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO role_permissions (organization_id, role_id, permission_code) "
            "SELECT organization_id, id, 'documents.review' FROM roles "
            "WHERE is_system IS TRUE AND name = 'Organization administrator' "
            "ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM role_permissions WHERE permission_code = 'documents.review'")
    )
    op.execute(sa.text("DELETE FROM permissions WHERE code = 'documents.review'"))
    for table in ("field_reviews", "evidence_anchors", "extracted_fields", "extractions"):
        op.drop_table(table)
    op.drop_constraint("uq_document_pages_parent_id", "document_pages", type_="unique")
