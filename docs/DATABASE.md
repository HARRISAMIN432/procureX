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

Later migrations add sourcing, supplier, evaluation, order, and finance aggregates
described in [DOMAIN.md](DOMAIN.md).

Budget balances are derived from an append-only four-bucket ledger: available, reserved,
committed, and consumed. Reservation locks the budget row, verifies the current available sum, and
writes balanced available/reserved deltas in the same transaction as final requisition approval.

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
