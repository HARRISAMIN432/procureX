"""Add purchase orders, receipts, invoice matching, and accounting export.

Revision ID: 20260920_0014
Revises: 20260920_0013
Create Date: 2026-09-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260920_0014"
down_revision: str | None = "20260920_0013"
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
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
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


def check_values(column: str, values: Sequence[str], name: str) -> sa.CheckConstraint:
    quoted = ",".join(f"'{value}'" for value in values)
    return sa.CheckConstraint(f"{column} IN ({quoted})", name=name)


def upgrade() -> None:
    op.create_table(
        "purchase_orders",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("award_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("po_number", sa.String(60), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("current_revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("total_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("creation_idempotency_key", sa.String(200), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint("version > 0", name="ck_purchase_orders_positive_version"),
        sa.CheckConstraint(
            "current_revision > 0", name="ck_purchase_orders_positive_current_revision"
        ),
        sa.CheckConstraint("total_amount >= 0", name="ck_purchase_orders_nonnegative_total_amount"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_purchase_orders_currency_iso_code"),
        sa.CheckConstraint(
            "length(content_digest) = 64", name="ck_purchase_orders_content_digest_length"
        ),
        check_values(
            "status",
            (
                "draft",
                "pending_authorization",
                "authorized",
                "issued",
                "acknowledged",
                "partially_received",
                "received",
                "cancelled",
                "closed",
            ),
            "ck_purchase_orders_purchase_order_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "award_id"],
            ["awards.organization_id", "awards.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id"),
        sa.UniqueConstraint("organization_id", "po_number"),
        sa.UniqueConstraint("organization_id", "award_id", "supplier_id"),
        sa.UniqueConstraint("organization_id", "creation_idempotency_key"),
    )
    op.create_table(
        "purchase_order_versions",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("total_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("material_change", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("amendment_reason", sa.Text()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("authorized_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("authorized_at", sa.DateTime(timezone=True)),
        sa.Column("issued_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledgement", sa.String(40)),
        sa.Column("acknowledgement_note", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("revision > 0", name="ck_purchase_order_versions_positive_revision"),
        sa.CheckConstraint(
            "total_amount >= 0", name="ck_purchase_order_versions_nonnegative_total_amount"
        ),
        sa.CheckConstraint(
            "length(content_digest) = 64",
            name="ck_purchase_order_versions_content_digest_length",
        ),
        check_values(
            "status",
            (
                "draft",
                "pending_authorization",
                "authorized",
                "issued",
                "acknowledged",
                "superseded",
            ),
            "ck_purchase_order_versions_purchase_order_version_status",
        ),
        sa.CheckConstraint(
            "acknowledgement IS NULL OR acknowledgement IN "
            "('accepted','rejected','changes_proposed')",
            name="ck_purchase_order_versions_supplier_acknowledgement",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "purchase_order_id"],
            ["purchase_orders.organization_id", "purchase_orders.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["authorized_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "purchase_order_id", "revision"),
        sa.UniqueConstraint("organization_id", "purchase_order_id", "id"),
        sa.UniqueConstraint("organization_id", "id"),
    )
    op.create_table(
        "purchase_order_lines",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rfq_item_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("unit_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("tax_amount", sa.Numeric(20, 4), server_default="0", nullable=False),
        sa.Column("freight_amount", sa.Numeric(20, 4), server_default="0", nullable=False),
        sa.Column("line_total", sa.Numeric(20, 4), nullable=False),
        sa.CheckConstraint("line_number > 0", name="ck_purchase_order_lines_positive_line_number"),
        sa.CheckConstraint("quantity > 0", name="ck_purchase_order_lines_positive_quantity"),
        sa.CheckConstraint(
            "unit_price >= 0", name="ck_purchase_order_lines_nonnegative_unit_price"
        ),
        sa.CheckConstraint(
            "tax_amount >= 0", name="ck_purchase_order_lines_nonnegative_tax_amount"
        ),
        sa.CheckConstraint(
            "freight_amount >= 0", name="ck_purchase_order_lines_nonnegative_freight_amount"
        ),
        sa.CheckConstraint(
            "line_total >= 0", name="ck_purchase_order_lines_nonnegative_line_total"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "purchase_order_id", "purchase_order_version_id"],
            [
                "purchase_order_versions.organization_id",
                "purchase_order_versions.purchase_order_id",
                "purchase_order_versions.id",
            ],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "rfq_item_id"],
            ["rfq_items.organization_id", "rfq_items.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "purchase_order_version_id", "line_number"),
        sa.UniqueConstraint("organization_id", "purchase_order_version_id", "id"),
        sa.UniqueConstraint("organization_id", "id"),
    )
    op.create_table(
        "delivery_receipts",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("receipt_number", sa.String(60), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("received_by_user_id", postgresql.UUID(as_uuid=True)),
        *timestamps(),
        sa.CheckConstraint("version > 0", name="ck_delivery_receipts_positive_version"),
        check_values(
            "status",
            ("recorded", "returned_in_part", "fully_returned"),
            "ck_delivery_receipts_delivery_receipt_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "purchase_order_id"],
            ["purchase_orders.organization_id", "purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "purchase_order_id", "purchase_order_version_id"],
            [
                "purchase_order_versions.organization_id",
                "purchase_order_versions.purchase_order_id",
                "purchase_order_versions.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["received_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id"),
        sa.UniqueConstraint("organization_id", "receipt_number"),
        sa.UniqueConstraint("organization_id", "idempotency_key"),
    )
    op.create_table(
        "delivery_receipt_lines",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("receipt_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("accepted_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("rejected_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("inspection_note", sa.Text()),
        sa.CheckConstraint(
            "accepted_quantity >= 0", name="ck_delivery_receipt_lines_nonnegative_accepted_quantity"
        ),
        sa.CheckConstraint(
            "rejected_quantity >= 0", name="ck_delivery_receipt_lines_nonnegative_rejected_quantity"
        ),
        sa.CheckConstraint(
            "accepted_quantity + rejected_quantity > 0",
            name="ck_delivery_receipt_lines_positive_delivered_quantity",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "receipt_id"],
            ["delivery_receipts.organization_id", "delivery_receipts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "purchase_order_version_id", "purchase_order_line_id"],
            [
                "purchase_order_lines.organization_id",
                "purchase_order_lines.purchase_order_version_id",
                "purchase_order_lines.id",
            ],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "receipt_id", "purchase_order_line_id"),
        sa.UniqueConstraint("organization_id", "id"),
    )
    op.create_table(
        "receipt_returns",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("receipt_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("returned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        *timestamps(),
        sa.CheckConstraint("quantity > 0", name="ck_receipt_returns_positive_quantity"),
        sa.ForeignKeyConstraint(
            ["organization_id", "receipt_line_id"],
            ["delivery_receipt_lines.organization_id", "delivery_receipt_lines.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id"),
        sa.UniqueConstraint("organization_id", "idempotency_key"),
    )
    op.create_table(
        "invoices",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_invoice_number", sa.String(120), nullable=False),
        sa.Column("normalized_invoice_number", sa.String(120), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("subtotal", sa.Numeric(20, 4), nullable=False),
        sa.Column("tax_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("freight_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("total_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("capture_idempotency_key", sa.String(200), nullable=False),
        sa.Column("captured_by_user_id", postgresql.UUID(as_uuid=True)),
        *timestamps(),
        sa.CheckConstraint("version > 0", name="ck_invoices_positive_version"),
        sa.CheckConstraint("subtotal >= 0", name="ck_invoices_nonnegative_subtotal"),
        sa.CheckConstraint("tax_amount >= 0", name="ck_invoices_nonnegative_tax_amount"),
        sa.CheckConstraint("freight_amount >= 0", name="ck_invoices_nonnegative_freight_amount"),
        sa.CheckConstraint("total_amount >= 0", name="ck_invoices_nonnegative_total_amount"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_invoices_currency_iso_code"),
        check_values(
            "status",
            (
                "captured",
                "duplicate_suspected",
                "matched",
                "mismatch",
                "approved_for_export",
                "exported",
                "voided",
            ),
            "ck_invoices_invoice_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "purchase_order_id"],
            ["purchase_orders.organization_id", "purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["suppliers.organization_id", "suppliers.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["captured_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id"),
        sa.UniqueConstraint("organization_id", "capture_idempotency_key"),
    )
    op.create_index(
        "ix_invoices_duplicate_review",
        "invoices",
        ["organization_id", "supplier_id", "normalized_invoice_number"],
    )
    op.create_table(
        "invoice_lines",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purchase_order_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(20, 4), nullable=False),
        sa.Column("tax_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("freight_amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("line_total", sa.Numeric(20, 4), nullable=False),
        sa.CheckConstraint("line_number > 0", name="ck_invoice_lines_positive_line_number"),
        sa.CheckConstraint("quantity > 0", name="ck_invoice_lines_positive_quantity"),
        sa.CheckConstraint("unit_price >= 0", name="ck_invoice_lines_nonnegative_unit_price"),
        sa.CheckConstraint("tax_amount >= 0", name="ck_invoice_lines_nonnegative_tax_amount"),
        sa.CheckConstraint(
            "freight_amount >= 0", name="ck_invoice_lines_nonnegative_freight_amount"
        ),
        sa.CheckConstraint("line_total >= 0", name="ck_invoice_lines_nonnegative_line_total"),
        sa.ForeignKeyConstraint(
            ["organization_id", "invoice_id"],
            ["invoices.organization_id", "invoices.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "purchase_order_line_id"],
            ["purchase_order_lines.organization_id", "purchase_order_lines.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "invoice_id", "line_number"),
        sa.UniqueConstraint("organization_id", "id"),
    )
    op.create_table(
        "invoice_matches",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(40), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("quantity_tolerance", sa.Numeric(18, 4), nullable=False),
        sa.Column("amount_tolerance", sa.Numeric(20, 4), nullable=False),
        sa.Column("percent_tolerance", sa.Numeric(8, 4), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("matched_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("attempt > 0", name="ck_invoice_matches_positive_attempt"),
        sa.CheckConstraint(
            "length(input_digest) = 64", name="ck_invoice_matches_input_digest_length"
        ),
        sa.CheckConstraint(
            "quantity_tolerance >= 0", name="ck_invoice_matches_nonnegative_quantity_tolerance"
        ),
        sa.CheckConstraint(
            "amount_tolerance >= 0", name="ck_invoice_matches_nonnegative_amount_tolerance"
        ),
        sa.CheckConstraint(
            "percent_tolerance >= 0 AND percent_tolerance <= 100",
            name="ck_invoice_matches_valid_percent_tolerance",
        ),
        check_values("mode", ("two_way", "three_way"), "ck_invoice_matches_invoice_match_mode"),
        check_values(
            "outcome", ("matched", "mismatch"), "ck_invoice_matches_invoice_match_outcome"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "invoice_id"],
            ["invoices.organization_id", "invoices.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["matched_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "invoice_id", "attempt"),
        sa.UniqueConstraint("organization_id", "idempotency_key"),
        sa.UniqueConstraint("organization_id", "id"),
    )
    op.create_table(
        "match_exceptions",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("match_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_line_id", postgresql.UUID(as_uuid=True)),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("blocking", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("expected_value", sa.String(200)),
        sa.Column("actual_value", sa.String(200)),
        sa.Column("variance", sa.Numeric(20, 4)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("resolution", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        check_values(
            "kind",
            ("duplicate_invoice", "currency", "quantity", "price", "tax", "freight", "total"),
            "ck_match_exceptions_match_exception_kind",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "match_id"],
            ["invoice_matches.organization_id", "invoice_matches.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "invoice_line_id"],
            ["invoice_lines.organization_id", "invoice_lines.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id"),
    )
    op.create_table(
        "accounting_exports",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(80), server_default="sandbox", nullable=False),
        sa.Column("external_reference", sa.String(120), nullable=False),
        sa.Column("external_id", sa.String(160)),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("reconciliation_status", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("exported_at", sa.DateTime(timezone=True)),
        sa.Column("reconciled_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        *timestamps(),
        sa.CheckConstraint("version > 0", name="ck_accounting_exports_positive_version"),
        sa.CheckConstraint(
            "attempt_count >= 0", name="ck_accounting_exports_nonnegative_attempt_count"
        ),
        sa.CheckConstraint(
            "length(payload_digest) = 64", name="ck_accounting_exports_payload_digest_length"
        ),
        check_values(
            "status",
            (
                "pending",
                "succeeded",
                "retry_scheduled",
                "failed",
                "reconciliation_required",
                "reconciled",
            ),
            "ck_accounting_exports_accounting_export_status",
        ),
        check_values(
            "reconciliation_status",
            ("pending", "reconciled", "mismatch"),
            "ck_accounting_exports_accounting_reconciliation_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "invoice_id"],
            ["invoices.organization_id", "invoices.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "invoice_id"),
        sa.UniqueConstraint("organization_id", "external_reference"),
        sa.UniqueConstraint("organization_id", "idempotency_key"),
        sa.UniqueConstraint("organization_id", "id"),
    )
    op.create_table(
        "accounting_sandbox_entries",
        uuid_pk(),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("export_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_reference", sa.String(120), nullable=False),
        sa.Column("external_id", sa.String(160), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "export_id"],
            ["accounting_exports.organization_id", "accounting_exports.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "external_reference"),
        sa.UniqueConstraint("organization_id", "export_id"),
        sa.UniqueConstraint("organization_id", "id"),
    )
    tables = (
        "purchase_orders",
        "purchase_order_versions",
        "purchase_order_lines",
        "delivery_receipts",
        "delivery_receipt_lines",
        "receipt_returns",
        "invoices",
        "invoice_lines",
        "invoice_matches",
        "match_exceptions",
        "accounting_exports",
        "accounting_sandbox_entries",
    )
    for table in tables:
        tenant_policy(table)
    permissions = {
        "orders.read": "View purchase orders and delivery history",
        "orders.write": "Create and amend purchase orders",
        "orders.approve": "Authorize material purchase-order amendments",
        "orders.issue": "Issue authorized purchase orders",
        "orders.acknowledge": "Record supplier purchase-order responses",
        "orders.receive": "Record deliveries, inspections, and returns",
        "invoices.read": "View supplier invoices and matching results",
        "invoices.write": "Capture supplier invoices",
        "invoices.match": "Run matching and resolve matching exceptions",
        "invoices.approve": "Approve matched invoices for export",
        "accounting.export": "Export approved invoices to accounting",
        "accounting.reconcile": "Record accounting reconciliation results",
    }
    for code, description in permissions.items():
        op.execute(
            sa.text(
                "INSERT INTO permissions (code, description) VALUES (:code, :description) "
                "ON CONFLICT (code) DO NOTHING"
            ).bindparams(code=code, description=description)
        )
    op.execute(
        sa.text(
            "INSERT INTO role_permissions (organization_id, role_id, permission_code) "
            "SELECT roles.organization_id, roles.id, permissions.code "
            "FROM roles CROSS JOIN permissions WHERE roles.is_system IS TRUE "
            "AND roles.name = 'Organization administrator' "
            "AND permissions.code LIKE ANY "
            "(ARRAY['orders.%','invoices.%','accounting.%']) ON CONFLICT DO NOTHING"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM role_permissions WHERE permission_code LIKE ANY "
            "(ARRAY['orders.%','invoices.%','accounting.%'])"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM permissions WHERE code LIKE ANY "
            "(ARRAY['orders.%','invoices.%','accounting.%'])"
        )
    )
    for table in (
        "accounting_sandbox_entries",
        "accounting_exports",
        "match_exceptions",
        "invoice_matches",
        "invoice_lines",
        "invoices",
        "receipt_returns",
        "delivery_receipt_lines",
        "delivery_receipts",
        "purchase_order_lines",
        "purchase_order_versions",
        "purchase_orders",
    ):
        op.drop_table(table)
