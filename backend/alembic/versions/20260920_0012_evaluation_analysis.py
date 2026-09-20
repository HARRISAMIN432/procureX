"""Bind durable AI analysis runs to immutable evaluations.

Revision ID: 20260920_0012
Revises: 20260919_0011
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260920_0012"
down_revision: str | None = "20260919_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_runs",
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_analysis_runs_evaluation",
        "analysis_runs",
        "evaluations",
        ["organization_id", "evaluation_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_analysis_runs_evaluation",
        "analysis_runs",
        ["organization_id", "evaluation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_analysis_runs_evaluation"), table_name="analysis_runs")
    op.drop_constraint(
        op.f("fk_analysis_runs_evaluation"), "analysis_runs", type_="foreignkey"
    )
    op.drop_column("analysis_runs", "evaluation_id")
