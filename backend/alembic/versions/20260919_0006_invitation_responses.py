"""Persist RFQ invitation response reasons.

Revision ID: 20260919_0006
Revises: 20260919_0005
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260919_0006"
down_revision: str | None = "20260919_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("rfq_invitations", sa.Column("response_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("rfq_invitations", "response_reason")
