"""Create approval policy and budget reservation controls.

Revision ID: 20260919_0003
Revises: 20260919_0002
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260919_0003"
down_revision: str | None = "20260919_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PERMISSIONS = {
    "budgets.read": "View budgets and ledger balances",
    "budgets.manage": "Create budgets and allocations",
    "budgets.reserve": "Reserve available budget during approval",
    "approvals.read": "View approval policies, requests, and decisions",
    "approvals.request": "Request approval for a submitted requisition",
    "approvals.decide": "Approve or reject assigned procurement decisions",
    "approvals.policies.manage": "Create and version approval policies",
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
        "budgets",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(30), server_default="active", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name=op.f("ck_budgets_currency_iso_code")),
        sa.CheckConstraint("period_end >= period_start", name=op.f("ck_budgets_valid_period")),
        sa.CheckConstraint("version > 0", name=op.f("ck_budgets_positive_version")),
        sa.CheckConstraint("status IN ('active','closed')", name=op.f("ck_budgets_budget_status")),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_budgets_org"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_budgets_creator",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_budgets"),
        sa.UniqueConstraint("organization_id", "code", name="uq_budgets_org_code"),
        sa.UniqueConstraint("organization_id", "id", name="uq_budgets_org_id"),
    )
    op.create_table(
        "approval_policies",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), server_default="active", nullable=False),
        sa.Column("minimum_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("maximum_amount", sa.Numeric(20, 4), nullable=True),
        sa.Column("required_approvals", sa.Integer(), nullable=False),
        sa.Column("prohibit_self_approval", sa.Boolean(), nullable=False),
        sa.Column("rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("version > 0", name=op.f("ck_approval_policies_positive_version")),
        sa.CheckConstraint(
            "required_approvals > 0",
            name=op.f("ck_approval_policies_positive_required_approvals"),
        ),
        sa.CheckConstraint(
            "minimum_amount >= 0",
            name=op.f("ck_approval_policies_nonnegative_minimum_amount"),
        ),
        sa.CheckConstraint(
            "maximum_amount IS NULL OR maximum_amount >= minimum_amount",
            name=op.f("ck_approval_policies_valid_amount_range"),
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name=op.f("ck_approval_policies_valid_effective_range"),
        ),
        sa.CheckConstraint(
            "status IN ('active','inactive')",
            name=op.f("ck_approval_policies_approval_policy_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_approval_policies_org",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_approval_policies_creator",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approval_policies"),
        sa.UniqueConstraint(
            "organization_id", "name", "version", name="uq_approval_policies_name_version"
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_approval_policies_org_id"),
    )
    op.create_table(
        "approval_requests",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requisition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requisition_version", sa.Integer(), nullable=False),
        sa.Column("snapshot_digest", sa.String(64), nullable=False),
        sa.Column("budget_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("requested_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("required_approvals", sa.Integer(), nullable=False),
        sa.Column("approval_count", sa.Integer(), nullable=False),
        sa.Column("prohibit_self_approval", sa.Boolean(), nullable=False),
        sa.Column("policy_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(30), server_default="pending", nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "requisition_version > 0",
            name=op.f("ck_approval_requests_positive_requisition_version"),
        ),
        sa.CheckConstraint(
            "requested_amount > 0", name=op.f("ck_approval_requests_positive_requested_amount")
        ),
        sa.CheckConstraint(
            "required_approvals > 0",
            name=op.f("ck_approval_requests_positive_required_approvals"),
        ),
        sa.CheckConstraint(
            "approval_count >= 0",
            name=op.f("ck_approval_requests_nonnegative_approval_count"),
        ),
        sa.CheckConstraint(
            "approval_count <= required_approvals",
            name=op.f("ck_approval_requests_approval_count_within_required"),
        ),
        sa.CheckConstraint(
            "policy_version > 0", name=op.f("ck_approval_requests_positive_policy_version")
        ),
        sa.CheckConstraint(
            "currency ~ '^[A-Z]{3}$'", name=op.f("ck_approval_requests_currency_iso_code")
        ),
        sa.CheckConstraint(
            "length(snapshot_digest) = 64",
            name=op.f("ck_approval_requests_snapshot_digest_length"),
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','cancelled','stale')",
            name=op.f("ck_approval_requests_approval_request_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requisition_id"],
            ["requisitions.organization_id", "requisitions.id"],
            ondelete="RESTRICT",
            name="fk_approval_requests_requisition",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "budget_id"],
            ["budgets.organization_id", "budgets.id"],
            ondelete="RESTRICT",
            name="fk_approval_requests_budget",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "policy_id"],
            ["approval_policies.organization_id", "approval_policies.id"],
            ondelete="RESTRICT",
            name="fk_approval_requests_policy",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_approval_requests_requester",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approval_requests"),
        sa.UniqueConstraint(
            "organization_id",
            "requisition_id",
            "requisition_version",
            name="uq_approval_requests_requisition_version",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_approval_requests_org_id"),
    )
    op.create_table(
        "approval_decisions",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approver_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(30), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approve','reject')",
            name=op.f("ck_approval_decisions_approval_decision_value"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "approval_request_id"],
            ["approval_requests.organization_id", "approval_requests.id"],
            ondelete="CASCADE",
            name="fk_approval_decisions_request",
        ),
        sa.ForeignKeyConstraint(
            ["approver_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_approval_decisions_approver",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approval_decisions"),
        sa.UniqueConstraint(
            "organization_id",
            "approval_request_id",
            "approver_user_id",
            name="uq_approval_decisions_approver",
        ),
    )
    op.create_table(
        "budget_ledger_entries",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("budget_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requisition_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("entry_type", sa.String(30), nullable=False),
        sa.Column("delta_available", sa.Numeric(20, 4), nullable=False),
        sa.Column("delta_reserved", sa.Numeric(20, 4), nullable=False),
        sa.Column("delta_committed", sa.Numeric(20, 4), nullable=False),
        sa.Column("delta_consumed", sa.Numeric(20, 4), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("reference_type", sa.String(100), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "delta_available <> 0 OR delta_reserved <> 0 OR delta_committed <> 0 "
            "OR delta_consumed <> 0",
            name=op.f("ck_budget_ledger_entries_nonzero_delta"),
        ),
        sa.CheckConstraint(
            "entry_type IN ('allocation','adjustment','reservation','release','commitment',"
            "'consumption')",
            name=op.f("ck_budget_ledger_entries_budget_entry_type"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "budget_id"],
            ["budgets.organization_id", "budgets.id"],
            ondelete="RESTRICT",
            name="fk_budget_ledger_entries_budget",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requisition_id"],
            ["requisitions.organization_id", "requisitions.id"],
            ondelete="RESTRICT",
            name="fk_budget_ledger_entries_requisition",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_budget_ledger_entries_actor",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_budget_ledger_entries"),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key", name="uq_budget_ledger_entries_idempotency"
        ),
    )
    op.create_table(
        "budget_reservations",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("budget_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requisition_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("approval_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("status", sa.String(30), server_default="active", nullable=False),
        *timestamps(),
        sa.CheckConstraint("amount > 0", name=op.f("ck_budget_reservations_positive_amount")),
        sa.CheckConstraint(
            "status IN ('active','released','committed')",
            name=op.f("ck_budget_reservations_budget_reservation_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "budget_id"],
            ["budgets.organization_id", "budgets.id"],
            ondelete="RESTRICT",
            name="fk_budget_reservations_budget",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requisition_id"],
            ["requisitions.organization_id", "requisitions.id"],
            ondelete="RESTRICT",
            name="fk_budget_reservations_requisition",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "approval_request_id"],
            ["approval_requests.organization_id", "approval_requests.id"],
            ondelete="RESTRICT",
            name="fk_budget_reservations_approval_request",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_budget_reservations"),
        sa.UniqueConstraint(
            "organization_id",
            "approval_request_id",
            name="uq_budget_reservations_approval_request",
        ),
    )

    for table in (
        "budgets",
        "approval_policies",
        "approval_requests",
        "approval_decisions",
        "budget_ledger_entries",
        "budget_reservations",
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
        "budget_reservations",
        "budget_ledger_entries",
        "approval_decisions",
        "approval_requests",
        "approval_policies",
        "budgets",
    ):
        op.drop_table(table)
