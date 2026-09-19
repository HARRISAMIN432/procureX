"""Add immutable deterministic offer evaluations.

Revision ID: 20260919_0010
Revises: 20260919_0009
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260919_0010"
down_revision: str | None = "20260919_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def uuid_pk() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False)


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
        "evaluations",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_rfq_version", sa.Integer(), nullable=False),
        sa.Column("publication_number", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("scoring_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.CheckConstraint("version > 0", name=op.f("ck_evaluations_positive_version")),
        sa.CheckConstraint(
            "source_rfq_version > 0",
            name=op.f("ck_evaluations_positive_source_rfq_version"),
        ),
        sa.CheckConstraint(
            "publication_number > 0",
            name=op.f("ck_evaluations_positive_publication_number"),
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name=op.f("ck_evaluations_currency_iso_code")
        ),
        sa.CheckConstraint(
            "length(content_digest) = 64",
            name=op.f("ck_evaluations_content_digest_length"),
        ),
        sa.CheckConstraint(
            "status IN ('completed')", name=op.f("ck_evaluations_evaluation_status")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id"],
            ["rfqs.organization_id", "rfqs.id"],
            ondelete="RESTRICT",
            name="fk_evaluations_rfq",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_evaluations_creator",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_evaluations"),
        sa.UniqueConstraint("organization_id", "rfq_id", "version", name="uq_evaluations_version"),
        sa.UniqueConstraint("organization_id", "rfq_id", "id", name="uq_evaluations_parent_id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_evaluations_org_id"),
    )
    op.create_table(
        "offer_evaluations",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("eligibility", sa.String(30), nullable=False),
        sa.Column("landed_cost", sa.Numeric(20, 4), nullable=False),
        sa.Column("preferred_ratio", sa.Numeric(7, 6), nullable=False),
        sa.Column("score", sa.Numeric(7, 4), nullable=True),
        sa.CheckConstraint(
            "eligibility IN ('eligible','ineligible','blocked')",
            name=op.f("ck_offer_evaluations_offer_eligibility"),
        ),
        sa.CheckConstraint(
            "landed_cost >= 0", name=op.f("ck_offer_evaluations_nonnegative_landed_cost")
        ),
        sa.CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 100)",
            name=op.f("ck_offer_evaluations_valid_score"),
        ),
        sa.CheckConstraint(
            "preferred_ratio >= 0 AND preferred_ratio <= 1",
            name=op.f("ck_offer_evaluations_valid_preferred_ratio"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "evaluation_id"],
            ["evaluations.organization_id", "evaluations.rfq_id", "evaluations.id"],
            ondelete="CASCADE",
            name="fk_offer_evaluations_evaluation",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "submission_id"],
            [
                "quote_submissions.organization_id",
                "quote_submissions.rfq_id",
                "quote_submissions.id",
            ],
            ondelete="RESTRICT",
            name="fk_offer_evaluations_submission",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="RESTRICT",
            name="fk_offer_evaluations_supplier",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_offer_evaluations"),
        sa.UniqueConstraint(
            "organization_id",
            "evaluation_id",
            "submission_id",
            name="uq_offer_evaluations_submission",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "rfq_id",
            "evaluation_id",
            "id",
            name="uq_offer_evaluations_parent_id",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_offer_evaluations_org_id"),
    )
    op.create_table(
        "requirement_checks",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offer_evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_requirement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.Column("is_mandatory", sa.Boolean(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('pass','fail','unknown','not_applicable')",
            name=op.f("ck_requirement_checks_requirement_check_outcome"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "evaluation_id", "offer_evaluation_id"],
            [
                "offer_evaluations.organization_id",
                "offer_evaluations.rfq_id",
                "offer_evaluations.evaluation_id",
                "offer_evaluations.id",
            ],
            ondelete="CASCADE",
            name="fk_requirement_checks_offer",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "rfq_requirement_id"],
            [
                "rfq_requirements.organization_id",
                "rfq_requirements.rfq_id",
                "rfq_requirements.id",
            ],
            ondelete="RESTRICT",
            name="fk_requirement_checks_requirement",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_requirement_checks"),
        sa.UniqueConstraint(
            "organization_id",
            "offer_evaluation_id",
            "rfq_requirement_id",
            name="uq_requirement_checks_requirement",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_requirement_checks_org_id"),
    )
    for table in ("evaluations", "offer_evaluations", "requirement_checks"):
        tenant_policy(table)
    op.execute(
        sa.text(
            "INSERT INTO permissions (code, description) VALUES "
            "('evaluations.read', 'View requirement matrices and evaluated offer comparisons'), "
            "('evaluations.run', 'Create deterministic offer evaluation snapshots') "
            "ON CONFLICT (code) DO NOTHING"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO role_permissions (organization_id, role_id, permission_code) "
            "SELECT organization_id, id, permission.code FROM roles "
            "CROSS JOIN (VALUES ('evaluations.read'), ('evaluations.run')) AS permission(code) "
            "WHERE is_system IS TRUE AND name = 'Organization administrator' "
            "ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM role_permissions "
            "WHERE permission_code IN ('evaluations.read', 'evaluations.run')"
        )
    )
    op.execute(
        sa.text("DELETE FROM permissions WHERE code IN ('evaluations.read', 'evaluations.run')")
    )
    for table in ("requirement_checks", "offer_evaluations", "evaluations"):
        op.drop_table(table)
