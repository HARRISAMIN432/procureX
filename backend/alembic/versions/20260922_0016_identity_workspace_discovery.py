"""Add RLS-safe authenticated workspace discovery.

Revision ID: 20260922_0016
Revises: 20260921_0015
Create Date: 2026-09-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260922_0016"
down_revision: str | None = "20260921_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION identity_workspaces(
            p_external_subject text,
            p_email text,
            p_email_verified boolean
        )
        RETURNS TABLE (
            organization_id uuid,
            organization_slug varchar(63),
            organization_name varchar(200),
            organization_status varchar(30),
            membership_id uuid,
            membership_status varchar(30),
            is_pending_invitation boolean
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public, pg_temp
        AS $$
            SELECT o.id,
                   o.slug,
                   o.name,
                   o.status::varchar(30),
                   m.id,
                   m.status::varchar(30),
                   (m.status = 'invited')
            FROM users AS u
            JOIN memberships AS m ON m.user_id = u.id
            JOIN organizations AS o ON o.id = m.organization_id
            WHERE (
                (u.external_subject = p_external_subject AND u.status = 'active')
                OR (
                    p_email_verified
                    AND p_email IS NOT NULL
                    AND u.external_subject IS NULL
                    AND u.status = 'invited'
                    AND lower(u.email) = lower(p_email)
                )
            )
              AND m.status IN ('active', 'invited')
              AND o.status IN ('active', 'closing')
        $$
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS identity_workspaces(text, text, boolean)")
