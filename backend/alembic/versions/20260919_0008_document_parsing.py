"""Add immutable parser/OCR results and pages.

Revision ID: 20260919_0008
Revises: 20260919_0007
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260919_0008"
down_revision: str | None = "20260919_0007"
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
    op.drop_constraint(
        "ck_document_versions_document_version_status",
        "document_versions",
        type_="check",
    )
    op.create_check_constraint(
        "document_version_status",
        "document_versions",
        "status IN ('quarantined','scanning','parsing','parsed','extracted','reviewed',"
        "'rejected','failed')",
    )
    op.create_table(
        "document_parses",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("result_key", sa.String(200), nullable=False),
        sa.Column("parser", sa.String(100), nullable=False),
        sa.Column("parser_version", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        *timestamps(),
        sa.CheckConstraint("version > 0", name=op.f("ck_document_parses_positive_version")),
        sa.CheckConstraint(
            "page_count >= 0", name=op.f("ck_document_parses_nonnegative_page_count")
        ),
        sa.CheckConstraint(
            "length(content_digest) = 64",
            name=op.f("ck_document_parses_content_digest_length"),
        ),
        sa.CheckConstraint(
            "kind IN ('native','ocr','hybrid')",
            name=op.f("ck_document_parses_document_parse_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('completed','failed')",
            name=op.f("ck_document_parses_document_parse_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            ondelete="CASCADE",
            name="fk_document_parses_document_version",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_parses"),
        sa.UniqueConstraint(
            "organization_id",
            "document_version_id",
            "version",
            name="uq_document_parses_version",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "document_version_id",
            "result_key",
            name="uq_document_parses_result_key",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "document_version_id",
            "id",
            name="uq_document_parses_parent_id",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_document_parses_org_id"),
    )
    op.create_table(
        "document_pages",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parse_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("source_label", sa.String(200), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("width", sa.Numeric(12, 4), nullable=True),
        sa.Column("height", sa.Numeric(12, 4), nullable=True),
        sa.Column("ocr_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("tables", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "page_number > 0", name=op.f("ck_document_pages_positive_page_number")
        ),
        sa.CheckConstraint(
            "width IS NULL OR width > 0", name=op.f("ck_document_pages_positive_width")
        ),
        sa.CheckConstraint(
            "height IS NULL OR height > 0", name=op.f("ck_document_pages_positive_height")
        ),
        sa.CheckConstraint(
            "ocr_confidence IS NULL OR (ocr_confidence >= 0 AND ocr_confidence <= 1)",
            name=op.f("ck_document_pages_valid_ocr_confidence"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id", "parse_id"],
            [
                "document_parses.organization_id",
                "document_parses.document_version_id",
                "document_parses.id",
            ],
            ondelete="CASCADE",
            name="fk_document_pages_parse",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_pages"),
        sa.UniqueConstraint(
            "organization_id", "parse_id", "page_number", name="uq_document_pages_page"
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_document_pages_org_id"),
    )
    tenant_policy("document_parses")
    tenant_policy("document_pages")
    op.execute(
        sa.text(
            "INSERT INTO permissions (code, description) VALUES "
            "('documents.process', 'Record trusted parser and OCR results') "
            "ON CONFLICT (code) DO NOTHING"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO role_permissions (organization_id, role_id, permission_code) "
            "SELECT organization_id, id, 'documents.process' FROM roles "
            "WHERE is_system IS TRUE AND name = 'Organization administrator' "
            "ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM role_permissions WHERE permission_code = 'documents.process'")
    )
    op.execute(sa.text("DELETE FROM permissions WHERE code = 'documents.process'"))
    op.drop_table("document_pages")
    op.drop_table("document_parses")
    op.drop_constraint(
        "ck_document_versions_document_version_status",
        "document_versions",
        type_="check",
    )
    op.create_check_constraint(
        "document_version_status",
        "document_versions",
        "status IN ('quarantined','scanning','parsing','extracted','reviewed',"
        "'rejected','failed')",
    )
