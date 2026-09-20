"""Add allocation scenarios and award approvals.

Revision ID: 20260920_0013
Revises: 20260920_0012
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260920_0013"
down_revision: str | None = "20260920_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


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
        "allocation_scenarios",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_evaluation_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("constraints", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("objective_amount", sa.Numeric(20, 4)),
        sa.Column("best_bound_amount", sa.Numeric(20, 4)),
        sa.Column("relative_gap", sa.Numeric(12, 8)),
        sa.Column("runtime_ms", sa.Integer(), nullable=False),
        sa.Column("independently_validated", sa.Boolean(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        *timestamps(),
        sa.CheckConstraint("version > 0", name="ck_allocation_scenarios_positive_version"),
        sa.CheckConstraint("runtime_ms >= 0", name="ck_allocation_scenarios_nonnegative_runtime"),
        sa.CheckConstraint(
            "length(source_evaluation_digest) = 64",
            name="ck_allocation_scenarios_source_digest_length",
        ),
        sa.CheckConstraint(
            "length(content_digest) = 64", name="ck_allocation_scenarios_content_digest_length"
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name="ck_allocation_scenarios_currency_iso_code"
        ),
        sa.CheckConstraint(
            "status IN ('optimal','feasible','infeasible','unknown','invalid')",
            name="ck_allocation_scenarios_allocation_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "evaluation_id"],
            ["evaluations.organization_id", "evaluations.rfq_id", "evaluations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "evaluation_id", "version"),
        sa.UniqueConstraint("organization_id", "rfq_id", "id"),
        sa.UniqueConstraint("organization_id", "id"),
    )
    op.create_table(
        "allocation_lines",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(20, 4), nullable=False),
        sa.Column("extended_cost", sa.Numeric(20, 4), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_allocation_lines_positive_quantity"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_allocation_lines_nonnegative_unit_cost"),
        sa.CheckConstraint(
            "extended_cost >= 0", name="ck_allocation_lines_nonnegative_extended_cost"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "scenario_id"],
            [
                "allocation_scenarios.organization_id",
                "allocation_scenarios.rfq_id",
                "allocation_scenarios.id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "submission_id"],
            [
                "quote_submissions.organization_id",
                "quote_submissions.rfq_id",
                "quote_submissions.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "rfq_item_id"],
            ["rfq_items.organization_id", "rfq_items.rfq_id", "rfq_items.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "scenario_id", "submission_id", "rfq_item_id"),
    )
    op.create_table(
        "awards",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("allocation_scenario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("total_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("dossier", postgresql.JSONB(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("required_approvals", sa.Integer(), nullable=False),
        sa.Column("approval_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("prohibit_self_approval", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint("version > 0", name="ck_awards_positive_version"),
        sa.CheckConstraint("total_amount >= 0", name="ck_awards_nonnegative_total_amount"),
        sa.CheckConstraint("required_approvals > 0", name="ck_awards_positive_required_approvals"),
        sa.CheckConstraint("approval_count >= 0", name="ck_awards_nonnegative_approval_count"),
        sa.CheckConstraint(
            "approval_count <= required_approvals", name="ck_awards_approval_count_within_required"
        ),
        sa.CheckConstraint("length(content_digest) = 64", name="ck_awards_content_digest_length"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_awards_currency_iso_code"),
        sa.CheckConstraint(
            "status IN ('draft','pending_approval','approved','rejected','stale','cancelled')",
            name="ck_awards_award_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "evaluation_id"],
            ["evaluations.organization_id", "evaluations.rfq_id", "evaluations.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_id", "allocation_scenario_id"],
            [
                "allocation_scenarios.organization_id",
                "allocation_scenarios.rfq_id",
                "allocation_scenarios.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "rfq_id", "version"),
        sa.UniqueConstraint("organization_id", "id"),
    )
    op.create_table(
        "award_decisions",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("award_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approve','reject')", name="ck_award_decisions_award_decision_value"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "award_id"],
            ["awards.organization_id", "awards.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["approver_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "award_id", "approver_user_id"),
    )
    for table in ("allocation_scenarios", "allocation_lines", "awards", "award_decisions"):
        tenant_policy(table)
    permissions = {
        "allocations.run": "Run and compare deterministic allocation scenarios",
        "awards.read": "View recommendation dossiers and award decisions",
        "awards.write": "Prepare and submit immutable award recommendations",
        "awards.approve": "Approve or reject award recommendations",
    }
    for code, description in permissions.items():
        op.execute(
            sa.text(
                "INSERT INTO permissions (code, description) "
                "VALUES (:code, :description) ON CONFLICT (code) DO NOTHING"
            ).bindparams(code=code, description=description)
        )
    op.execute(
        sa.text(
            "INSERT INTO role_permissions (organization_id, role_id, permission_code) "
            "SELECT roles.organization_id, roles.id, permissions.code "
            "FROM roles CROSS JOIN permissions WHERE roles.is_system IS TRUE "
            "AND roles.name = 'Organization administrator' "
            "AND permissions.code IN "
            "('allocations.run','awards.read','awards.write','awards.approve') "
            "ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_code IN "
            "('allocations.run','awards.read','awards.write','awards.approve')"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM permissions WHERE code IN "
            "('allocations.run','awards.read','awards.write','awards.approve')"
        )
    )
    for table in ("award_decisions", "awards", "allocation_lines", "allocation_scenarios"):
        op.drop_table(table)
