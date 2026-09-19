# Database

## Technology

PostgreSQL is the authoritative store. The backend uses SQLAlchemy 2 async sessions and Alembic.
Application runtime roles must not be superusers, table owners, or hold `BYPASSRLS`.
SQLAlchemy uses an `asyncpg` URL; LangGraph's PostgreSQL checkpointer receives a separate
`psycopg`-compatible `postgresql://` URL.

## Foundation tables

| Area | Tables |
|---|---|
| Identity | `organizations`, `users`, `memberships`, `roles`, `permissions`, `role_permissions`, `membership_roles` |
| Configuration | `organization_settings` |
| Documents | `documents`, `document_versions`, `cloudinary_assets`, `document_scans` |
| AI execution | `analysis_runs`, `model_invocations` |
| Platform | `jobs`, `outbox_events`, `audit_events` |
| Requisitions | `requisitions`, `requisition_lines`, `requisition_requirements`, `requisition_revisions` |
| Approval controls | `approval_policies`, `approval_requests`, `approval_decisions` |
| Budgets | `budgets`, `budget_ledger_entries`, `budget_reservations` |
| Suppliers | `suppliers`, `supplier_contacts`, `supplier_qualifications`, `supplier_certificates` |
| Sourcing | `rfqs`, `rfq_items`, `rfq_requirements`, `rfq_revisions`, `rfq_invitations`, `quote_submissions`, `quote_lines`, `rfq_clarifications` |

Later migrations add evaluation, order, and finance aggregates
described in [DOMAIN.md](DOMAIN.md).

Budget balances are derived from an append-only four-bucket ledger: available, reserved,
committed, and consumed. Reservation locks the budget row, verifies the current available sum, and
writes balanced available/reserved deltas in the same transaction as final requisition approval.

Supplier records are buyer-organization scoped. Registration identity is unique within a tenant;
contacts, category qualifications, and certificates remain subordinate tenant-owned records.
Profile changes to an approved supplier require reapproval. Certificate metadata may reference an
immutable document version, while the file remains an authenticated Cloudinary asset.

An RFQ is created from one approved requisition and copies its lines and requirements into the
sourcing boundary. Publication and every amendment create an immutable JSON snapshot with a
SHA-256 digest. Invitations point to the current published revision; each immutable quote version
retains the exact revision it answered. Quote lines use composite tenant/parent foreign keys so a
line cannot reference another RFQ's item or submission.

## Tenant isolation

Tenant tables carry a non-null `organization_id`. PostgreSQL row-level security reads the current
tenant from the transaction-local `app.current_organization_id` setting. The API derives this ID
from an authenticated membership and calls `tenant_transaction`; it never trusts a tenant ID in a
payload. Connection-pool reuse is safe because the value is transaction-local.

Global tables are limited to `users` and the permission catalog. Organization lookup during
authenticated context selection requires a narrowly scoped path; ordinary domain access occurs
after tenant context is established.

## Migration rules

1. Generate an Alembic revision for every schema change.
2. Use expand/migrate/contract changes for deployed data.
3. Test upgrades against realistic data and produce offline SQL in CI.
4. Do not edit a revision after it has reached a shared environment.
5. Add constraints before relying on an invariant in application code.
6. Include RLS policy changes and downgrade implications in review.

## Cloudinary metadata

`cloudinary_assets` stores stable provider identifiers and metadata, not delivery URLs. Assets must
use `authenticated` delivery, overwrite is disabled, and each `document_version` owns one asset.
The application authorizes every access before generating a short-lived signed URL.
