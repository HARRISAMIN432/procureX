"""Add durable invitation email delivery state.

Revision ID: 20260922_0017
Revises: 20260922_0016
Create Date: 2026-09-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260922_0017"
down_revision: str | None = "20260922_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memberships",
        sa.Column(
            "invitation_email_status",
            sa.String(30),
            server_default="not_applicable",
            nullable=False,
        ),
    )
    op.add_column(
        "memberships",
        sa.Column("invitation_email_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "memberships", sa.Column("invitation_email_provider_id", sa.String(255))
    )
    op.add_column(
        "memberships", sa.Column("invitation_email_error_code", sa.String(100))
    )
    op.add_column(
        "memberships", sa.Column("invitation_email_sent_at", sa.DateTime(timezone=True))
    )
    op.create_check_constraint(
        "membership_invitation_email_status",
        "memberships",
        "invitation_email_status IN "
        "('not_applicable','queued','sending','sent','retry_scheduled','failed')",
    )
    op.create_check_constraint(
        "membership_invitation_email_attempts",
        "memberships",
        "invitation_email_attempts >= 0",
    )
    op.create_index(
        "ix_memberships_invitation_email_status",
        "memberships",
        ["organization_id", "invitation_email_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_memberships_invitation_email_status", table_name="memberships")
    op.drop_constraint(
        "ck_memberships_membership_invitation_email_attempts",
        "memberships",
        type_="check",
    )
    op.drop_constraint(
        "ck_memberships_membership_invitation_email_status",
        "memberships",
        type_="check",
    )
    op.drop_column("memberships", "invitation_email_sent_at")
    op.drop_column("memberships", "invitation_email_error_code")
    op.drop_column("memberships", "invitation_email_provider_id")
    op.drop_column("memberships", "invitation_email_attempts")
    op.drop_column("memberships", "invitation_email_status")
