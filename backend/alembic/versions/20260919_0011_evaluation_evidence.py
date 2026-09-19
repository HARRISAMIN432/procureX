"""Link quote documents to evidence-backed evaluation checks.

Revision ID: 20260919_0011
Revises: 20260919_0010
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260919_0011"
down_revision: str | None = "20260919_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


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
        "uq_requirement_checks_parent_id",
        "requirement_checks",
        ["organization_id", "evaluation_id", "id"],
    )
    op.create_table(
        "quote_submission_documents",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "submission_id"],
            [
                "quote_submissions.organization_id",
                "quote_submissions.rfq_id",
                "quote_submissions.id",
            ],
            ondelete="CASCADE",
            name="fk_quote_submission_documents_submission",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            ondelete="RESTRICT",
            name="fk_quote_submission_documents_document_version",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_quote_submission_documents"),
        sa.UniqueConstraint(
            "organization_id",
            "submission_id",
            "document_version_id",
            name="uq_quote_submission_documents_version",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_quote_submission_documents_org_id"),
    )
    op.create_table(
        "requirement_check_evidence",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requirement_check_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_anchor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "evaluation_id", "requirement_check_id"],
            [
                "requirement_checks.organization_id",
                "requirement_checks.evaluation_id",
                "requirement_checks.id",
            ],
            ondelete="CASCADE",
            name="fk_requirement_check_evidence_check",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "evidence_anchor_id"],
            ["evidence_anchors.organization_id", "evidence_anchors.id"],
            ondelete="RESTRICT",
            name="fk_requirement_check_evidence_anchor",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_requirement_check_evidence"),
        sa.UniqueConstraint(
            "organization_id",
            "requirement_check_id",
            "evidence_anchor_id",
            name="uq_requirement_check_evidence_anchor",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_requirement_check_evidence_org_id"),
    )
    tenant_policy("quote_submission_documents")
    tenant_policy("requirement_check_evidence")


def downgrade() -> None:
    op.drop_table("requirement_check_evidence")
    op.drop_table("quote_submission_documents")
    op.drop_constraint("uq_requirement_checks_parent_id", "requirement_checks", type_="unique")
