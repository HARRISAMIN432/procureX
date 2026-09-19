"""Create identity, document, AI, and platform foundation tables.

Revision ID: 20260919_0001
Revises: None
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260919_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


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


def tenant_policy(table: str, identity_column: str = "organization_id") -> None:
    tenant = "NULLIF(current_setting('app.current_organization_id', true), '')::uuid"
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY "tenant_isolation_{table}" ON "{table}" '
            f'USING ("{identity_column}" = {tenant}) '
            f'WITH CHECK ("{identity_column}" = {tenant})'
        )
    )


def upgrade() -> None:
    op.create_table(
        "organizations",
        uuid_pk(),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(30), server_default="active", nullable=False),
        sa.Column("default_currency", sa.String(3), server_default="PKR", nullable=False),
        sa.Column("timezone", sa.String(64), server_default="Asia/Karachi", nullable=False),
        *timestamps(),
        sa.CheckConstraint("slug = lower(slug)", name=op.f("ck_organizations_slug_lowercase")),
        sa.CheckConstraint(
            "default_currency ~ '^[A-Z]{3}$'", name=op.f("ck_organizations_currency_iso_code")
        ),
        sa.CheckConstraint(
            "status IN ('active','suspended','closing','closed')",
            name=op.f("ck_organizations_organization_status"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organizations"),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_table(
        "users",
        uuid_pk(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("external_subject", sa.String(255), nullable=True),
        sa.Column("status", sa.String(30), server_default="invited", nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('invited','active','suspended','disabled')",
            name=op.f("ck_users_user_status"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("external_subject", name="uq_users_external_subject"),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)
    op.create_table(
        "permissions",
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_permissions"),
    )
    op.create_table(
        "memberships",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(30), server_default="invited", nullable=False),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('invited','active','suspended','revoked')",
            name=op.f("ck_memberships_membership_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_memberships_org"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="fk_memberships_user"
        ),
        sa.ForeignKeyConstraint(
            ["invited_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_memberships_inviter",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memberships"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_memberships_org_user"),
        sa.UniqueConstraint("organization_id", "id", name="uq_memberships_org_id"),
    )
    op.create_table(
        "roles",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_roles_org"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_roles"),
        sa.UniqueConstraint("organization_id", "name", name="uq_roles_org_name"),
        sa.UniqueConstraint("organization_id", "id", name="uq_roles_org_id"),
    )
    op.create_table(
        "role_permissions",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permission_code", sa.String(120), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "role_id"],
            ["roles.organization_id", "roles.id"],
            ondelete="CASCADE",
            name="fk_role_permissions_role",
        ),
        sa.ForeignKeyConstraint(
            ["permission_code"],
            ["permissions.code"],
            ondelete="CASCADE",
            name="fk_role_permissions_permission",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "role_id", "permission_code", name="pk_role_permissions"
        ),
    )
    op.create_table(
        "membership_roles",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("membership_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "membership_id"],
            ["memberships.organization_id", "memberships.id"],
            ondelete="CASCADE",
            name="fk_membership_roles_membership",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "role_id"],
            ["roles.organization_id", "roles.id"],
            ondelete="CASCADE",
            name="fk_membership_roles_role",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "membership_id", "role_id", name="pk_membership_roles"
        ),
    )
    op.create_table(
        "organization_settings",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("settings", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("version > 0", name=op.f("ck_organization_settings_positive_version")),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name=op.f("ck_organization_settings_valid_effective_range"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_organization_settings_org",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_organization_settings_creator",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_organization_settings"),
        sa.UniqueConstraint(
            "organization_id", "version", name="uq_organization_settings_org_version"
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_organization_settings_org_id"),
    )
    op.create_table(
        "documents",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("document_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), server_default="quarantined", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('quarantined','scanning','ready','rejected','archived')",
            name=op.f("ck_documents_document_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_documents_org"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_documents_creator",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.UniqueConstraint("organization_id", "id", name="uq_documents_org_id"),
    )
    op.create_table(
        "document_versions",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("media_type", sa.String(150), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), server_default="quarantined", nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint("version > 0", name=op.f("ck_document_versions_positive_version")),
        sa.CheckConstraint(
            "byte_size >= 0", name=op.f("ck_document_versions_nonnegative_byte_size")
        ),
        sa.CheckConstraint("length(sha256) = 64", name=op.f("ck_document_versions_sha256_length")),
        sa.CheckConstraint(
            "status IN ('quarantined','scanning','parsing','extracted',"
            "'reviewed','rejected','failed')",
            name=op.f("ck_document_versions_document_version_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            ondelete="CASCADE",
            name="fk_document_versions_document",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_document_versions_creator",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_versions"),
        sa.UniqueConstraint(
            "organization_id", "document_id", "version", name="uq_document_versions_version"
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_document_versions_org_id"),
    )
    op.create_table(
        "cloudinary_assets",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cloudinary_asset_id", sa.String(255), nullable=False),
        sa.Column("public_id", sa.String(500), nullable=False),
        sa.Column("resource_type", sa.String(20), nullable=False),
        sa.Column("delivery_type", sa.String(20), server_default="authenticated", nullable=False),
        sa.Column("provider_version", sa.BigInteger(), nullable=False),
        sa.Column("format", sa.String(50), nullable=True),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("upload_response_signature", sa.String(255), nullable=True),
        sa.Column("backup_enabled", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(30), server_default="uploaded", nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "delivery_type = 'authenticated'",
            name=op.f("ck_cloudinary_assets_authenticated_delivery"),
        ),
        sa.CheckConstraint(
            "byte_size >= 0", name=op.f("ck_cloudinary_assets_nonnegative_byte_size")
        ),
        sa.CheckConstraint(
            "status IN ('uploaded','verified','deletion_pending','deleted','missing')",
            name=op.f("ck_cloudinary_assets_cloudinary_asset_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            ondelete="CASCADE",
            name="fk_cloudinary_assets_document_version",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cloudinary_assets"),
        sa.UniqueConstraint("cloudinary_asset_id", name="uq_cloudinary_assets_asset_id"),
        sa.UniqueConstraint(
            "organization_id", "document_version_id", name="uq_cloudinary_assets_document_version"
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_cloudinary_assets_org_id"),
    )
    op.create_index("ix_cloudinary_assets_public_id", "cloudinary_assets", ["public_id"])
    op.create_table(
        "document_scans",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scanner", sa.String(100), nullable=False),
        sa.Column("scanner_version", sa.String(100), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('pending','clean','infected','error')",
            name=op.f("ck_document_scans_document_scan_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            ondelete="CASCADE",
            name="fk_document_scans_document_version",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_scans"),
        sa.UniqueConstraint(
            "organization_id",
            "document_version_id",
            "scanner",
            "scanner_version",
            name="uq_document_scans_version_scanner",
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_document_scans_org_id"),
    )
    op.create_table(
        "analysis_runs",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("graph_name", sa.String(120), nullable=False),
        sa.Column("graph_version", sa.String(80), nullable=False),
        sa.Column("thread_id", sa.String(255), nullable=False),
        sa.Column("document_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_digest", sa.String(128), nullable=False),
        sa.Column("status", sa.String(30), server_default="queued", nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('queued','running','awaiting_review','completed',"
            "'failed','cancelled','stale')",
            name=op.f("ck_analysis_runs_analysis_run_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_analysis_runs_org",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            ondelete="RESTRICT",
            name="fk_analysis_runs_document_version",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_analysis_runs_creator",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_analysis_runs"),
        sa.UniqueConstraint("organization_id", "thread_id", name="uq_analysis_runs_thread"),
        sa.UniqueConstraint("organization_id", "id", name="uq_analysis_runs_org_id"),
    )
    op.create_table(
        "model_invocations",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("analysis_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_name", sa.String(120), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cost_amount", sa.Numeric(18, 8), nullable=False),
        sa.Column("cost_currency", sa.String(3), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("provider_request_id", sa.String(255), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        *timestamps(),
        sa.CheckConstraint(
            "input_tokens >= 0", name=op.f("ck_model_invocations_nonnegative_input_tokens")
        ),
        sa.CheckConstraint(
            "output_tokens >= 0", name=op.f("ck_model_invocations_nonnegative_output_tokens")
        ),
        sa.CheckConstraint("cost_amount >= 0", name=op.f("ck_model_invocations_nonnegative_cost")),
        sa.CheckConstraint(
            "status IN ('started','completed','failed')",
            name=op.f("ck_model_invocations_model_invocation_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "analysis_run_id"],
            ["analysis_runs.organization_id", "analysis_runs.id"],
            ondelete="CASCADE",
            name="fk_model_invocations_analysis_run",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_model_invocations"),
        sa.UniqueConstraint("organization_id", "id", name="uq_model_invocations_org_id"),
    )
    op.create_table(
        "jobs",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(120), nullable=False),
        sa.Column("status", sa.String(30), server_default="queued", nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        *timestamps(),
        sa.CheckConstraint("attempts >= 0", name=op.f("ck_jobs_nonnegative_attempts")),
        sa.CheckConstraint("max_attempts > 0", name=op.f("ck_jobs_positive_max_attempts")),
        sa.CheckConstraint(
            "status IN ('queued','running','retry_scheduled','completed','failed','cancelled')",
            name=op.f("ck_jobs_job_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE", name="fk_jobs_org"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.UniqueConstraint("organization_id", "idempotency_key", name="uq_jobs_idempotency"),
        sa.UniqueConstraint("organization_id", "id", name="uq_jobs_org_id"),
    )
    op.create_index("ix_jobs_claim", "jobs", ["status", "scheduled_at"])
    op.create_table(
        "outbox_events",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(160), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("causation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_attempts", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "aggregate_version > 0", name=op.f("ck_outbox_events_positive_aggregate_version")
        ),
        sa.CheckConstraint(
            "publish_attempts >= 0", name=op.f("ck_outbox_events_nonnegative_publish_attempts")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="CASCADE",
            name="fk_outbox_events_org",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_events"),
        sa.UniqueConstraint(
            "organization_id",
            "aggregate_id",
            "aggregate_version",
            "event_type",
            name="uq_outbox_events_aggregate_version",
        ),
    )
    op.create_index(
        "ix_outbox_events_unpublished",
        "outbox_events",
        ["occurred_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_table(
        "audit_events",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_type", sa.String(30), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(160), nullable=False),
        sa.Column("object_type", sa.String(100), nullable=False),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("object_version", sa.Integer(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(100), nullable=True),
        sa.Column("correlation_id", sa.String(100), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "actor_type IN ('user','service','system')",
            name=op.f("ck_audit_events_audit_actor_type"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            ondelete="RESTRICT",
            name="fk_audit_events_org",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )
    op.create_index(
        "ix_audit_events_object",
        "audit_events",
        ["organization_id", "object_type", "object_id"],
    )
    op.create_index("ix_audit_events_occurred", "audit_events", ["organization_id", "occurred_at"])

    tenant_policy("organizations", "id")
    for table in (
        "memberships",
        "roles",
        "role_permissions",
        "membership_roles",
        "organization_settings",
        "documents",
        "document_versions",
        "cloudinary_assets",
        "document_scans",
        "analysis_runs",
        "model_invocations",
        "jobs",
        "outbox_events",
        "audit_events",
    ):
        tenant_policy(table)


def downgrade() -> None:
    for table in (
        "audit_events",
        "outbox_events",
        "jobs",
        "model_invocations",
        "analysis_runs",
        "document_scans",
        "cloudinary_assets",
        "document_versions",
        "documents",
        "organization_settings",
        "membership_roles",
        "role_permissions",
        "roles",
        "memberships",
        "permissions",
        "users",
        "organizations",
    ):
        op.drop_table(table)
