"""Add subscription, lifecycle, support, and after-sales records.

Revision ID: 20260921_0015
Revises: 20260920_0014
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260921_0015"
down_revision: str | None = "20260920_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        nullable=False,
    )


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def _tenant(table: str) -> None:
    tenant = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY "tenant_isolation_{table}" ON "{table}" '
            f"USING (organization_id = {tenant}) "
            f"WITH CHECK (organization_id = {tenant})"
        )
    )


def upgrade() -> None:
    op.create_table(
        "organization_subscriptions",
        _id(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_code", sa.String(50), server_default="community", nullable=False),
        sa.Column("status", sa.String(30), server_default="active", nullable=False),
        sa.Column("billing_mode", sa.String(30), server_default="manual", nullable=False),
        sa.Column("seat_limit", sa.Integer(), server_default="5", nullable=False),
        sa.Column(
            "storage_limit_bytes", sa.BigInteger(), server_default="536870912", nullable=False
        ),
        sa.Column("ai_run_limit_monthly", sa.Integer(), server_default="25", nullable=False),
        sa.Column(
            "entitlements",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.CheckConstraint(
            "seat_limit > 0", name="ck_organization_subscriptions_positive_seat_limit"
        ),
        sa.CheckConstraint(
            "storage_limit_bytes > 0", name="ck_organization_subscriptions_positive_storage_limit"
        ),
        sa.CheckConstraint(
            "ai_run_limit_monthly >= 0",
            name="ck_organization_subscriptions_nonnegative_ai_run_limit",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id"),
    )
    op.create_table(
        "data_export_requests",
        _id(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(30), server_default="completed", nullable=False),
        sa.Column("format", sa.String(20), server_default="json", nullable=False),
        sa.Column(
            "manifest", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id"),
    )
    op.create_table(
        "organization_closure_requests",
        _id(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(30), server_default="scheduled", nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id"),
    )
    op.create_table(
        "support_cases",
        _id(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_number", sa.String(40), nullable=False),
        sa.Column("requester_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(20), server_default="normal", nullable=False),
        sa.Column("status", sa.String(30), server_default="open", nullable=False),
        sa.Column("resolution", sa.Text()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id"),
        sa.UniqueConstraint("organization_id", "case_number"),
    )
    op.create_table(
        "after_sales_cases",
        _id(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_number", sa.String(40), nullable=False),
        sa.Column("case_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), server_default="open", nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("resolution", sa.Text()),
        sa.Column("financial_impact", sa.Numeric(20, 4), server_default="0", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.CheckConstraint(
            "financial_impact >= 0", name="ck_after_sales_cases_nonnegative_financial_impact"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "purchase_order_id"],
            ["purchase_orders.organization_id", "purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id"),
        sa.UniqueConstraint("organization_id", "case_number"),
    )
    for table in (
        "organization_subscriptions",
        "data_export_requests",
        "organization_closure_requests",
        "support_cases",
        "after_sales_cases",
    ):
        _tenant(table)


def downgrade() -> None:
    for table in (
        "after_sales_cases",
        "support_cases",
        "organization_closure_requests",
        "data_export_requests",
        "organization_subscriptions",
    ):
        op.drop_table(table)
