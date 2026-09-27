"""Track RFQ invitation email delivery per published revision.

Revision ID: 20260927_0019
Revises: 20260927_0018
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260927_0019"
down_revision: str | None = "20260927_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "rfq_invitations",
        sa.Column("email_status", sa.String(30), server_default="not_applicable", nullable=False),
    )
    op.add_column(
        "rfq_invitations",
        sa.Column("email_publication_number", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "rfq_invitations",
        sa.Column("email_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("rfq_invitations", sa.Column("email_provider_id", sa.String(255)))
    op.add_column("rfq_invitations", sa.Column("email_error_code", sa.String(100)))
    op.add_column("rfq_invitations", sa.Column("email_sent_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_rfq_invitations_email_status",
        "rfq_invitations",
        "email_status IN ('not_applicable','queued','sending','sent','retry_scheduled','failed')",
    )
    op.create_check_constraint(
        "ck_rfq_invitations_email_publication",
        "rfq_invitations",
        "email_publication_number >= 0 AND email_attempts >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_rfq_invitations_email_publication", "rfq_invitations", type_="check")
    op.drop_constraint("ck_rfq_invitations_email_status", "rfq_invitations", type_="check")
    for column in (
        "email_sent_at",
        "email_error_code",
        "email_provider_id",
        "email_attempts",
        "email_publication_number",
        "email_status",
    ):
        op.drop_column("rfq_invitations", column)
