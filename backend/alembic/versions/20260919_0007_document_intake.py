"""Add secure document upload intent expiry and scan permission.

Revision ID: 20260919_0007
Revises: 20260919_0006
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260919_0007"
down_revision: str | None = "20260919_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

def upgrade() -> None:
    op.add_column(
        "document_versions",
        sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        sa.text(
            "INSERT INTO permissions (code, description) VALUES "
            "('documents.scan', 'Record trusted malware scan results') "
            "ON CONFLICT (code) DO NOTHING"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO role_permissions (organization_id, role_id, permission_code) "
            "SELECT organization_id, id, 'documents.scan' FROM roles "
            "WHERE is_system IS TRUE AND name = 'Organization administrator' "
            "ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM role_permissions WHERE permission_code = 'documents.scan'")
    )
    op.execute(sa.text("DELETE FROM permissions WHERE code = 'documents.scan'"))
    op.drop_column("document_versions", "upload_expires_at")
