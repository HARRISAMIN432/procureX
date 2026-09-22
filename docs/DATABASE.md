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
| Documents | `documents`, `document_versions`, `cloudinary_assets`, `document_scans`, `document_parses`, `document_pages`, `extractions`, `extracted_fields`, `evidence_anchors`, `field_reviews` |
| AI execution | `analysis_runs`, `model_invocations` |
| Platform | `jobs`, `outbox_events`, `audit_events` |
| Requisitions | `requisitions`, `requisition_lines`, `requisition_requirements`, `requisition_revisions` |
| Approval controls | `approval_policies`, `approval_requests`, `approval_decisions` |
| Budgets | `budgets`, `budget_ledger_entries`, `budget_reservations` |
| Suppliers | `suppliers`, `supplier_contacts`, `supplier_qualifications`, `supplier_certificates` |
| Sourcing | `rfqs`, `rfq_items`, `rfq_requirements`, `rfq_revisions`, `rfq_invitations`, `quote_submissions`, `quote_lines`, `quote_submission_documents`, `rfq_clarifications` |
| Evaluation | `evaluations`, `offer_evaluations`, `requirement_checks`, `requirement_check_evidence` |
| Allocation and awards | `allocation_scenarios`, `allocation_lines`, `awards`, `award_decisions` |
| Order operations | `purchase_orders`, `purchase_order_versions`, `purchase_order_lines`, `delivery_receipts`, `delivery_receipt_lines`, `receipt_returns` |
| Invoice matching | `invoices`, `invoice_lines`, `invoice_matches`, `match_exceptions` |
| Accounting integration | `accounting_exports`, `accounting_sandbox_entries` |

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
line cannot reference another RFQ's item or submission. Invitation rows retain acknowledgement or
no-bid response time and the supplier's no-bid reason; response commands also increment the RFQ
aggregate version so concurrent actions cannot silently overwrite one another.

An `evaluation` is an immutable, monotonically versioned comparison of a closed RFQ. Its canonical
snapshot binds the RFQ/publication version, scoring weights, current quote IDs and digests,
requirement matrix, exact landed costs, eligibility, and scores under one SHA-256 digest.
`offer_evaluations` retain calculated offer results; `requirement_checks` preserve every outcome,
mandatory flag, and reviewer rationale. `quote_submission_documents` freezes which immutable
document versions accompany a quote. `requirement_check_evidence` can reference only tenant-owned
anchors, while application validation additionally requires the anchor's field to be verified,
its extraction completed, and its document attached to the assessed quote. Tenant-qualified
foreign keys prevent an evaluation from mixing RFQs, submissions, suppliers, requirements, or
evidence across ownership boundaries.

An `allocation_scenario` is an immutable solver run bound to one evaluation digest and one exact
constraint set. Its lines preserve selected submission, supplier, RFQ item, quantity, normalized
unit cost, and extended cost. An `award` binds one independently validated feasible scenario to an
immutable recommendation dossier and approval-policy snapshot. `award_decisions` are append-only
and unique per approver and award; changed selected-source inputs move a pending award to `stale`.

An issued PO is represented by a mutable workflow header and immutable revision rows. Tenant-scoped
composite foreign keys bind every PO to its award/supplier, every line to its version/RFQ item, and
every receipt and invoice line to a line owned by the same organization. Unique command keys
enforce idempotency. The one-export-per-invoice and stable external-reference constraints provide
the final duplicate barrier for the accounting sandbox. All twelve P7 tables have forced RLS.

## Tenant isolation

Tenant tables carry a non-null `organization_id`. PostgreSQL row-level security reads the current
tenant from the transaction-local `app.current_organization_id` setting. The API derives this ID
from an authenticated membership and calls `tenant_transaction`; it never trusts a tenant ID in a
payload. Connection-pool reuse is safe because the value is transaction-local.

Global tables are limited to `users` and the permission catalog. Organization lookup during
authenticated context selection requires a narrowly scoped path; ordinary domain access occurs
after tenant context is established.

Each membership also carries invitation delivery state (`queued`, `sending`, `sent`,
`retry_scheduled`, or `failed`), a bounded attempt count, safe failure code, provider message ID,
and provider-acceptance timestamp. This makes retries and administrator visibility durable without
storing message content or provider credentials.

## Migration rules

1. Generate an Alembic revision for every schema change.
2. Use expand/migrate/contract changes for deployed data.
3. Test upgrades against realistic data and produce offline SQL in CI.
4. Do not edit a revision after it has reached a shared environment.
5. Add constraints before relying on an invariant in application code.
6. Include RLS policy changes and downgrade implications in review.

## Backup and restore drills

The non-production administrative CLI creates PostgreSQL custom archives with a separate
SHA-256/size manifest, private file permissions, and no credentials in command arguments or output.
Restore verifies the manifest and archive listing before using one transaction against an
explicitly confirmed empty target; it never uses `--clean` or `--create`. The tool fails closed in
production, where managed encrypted backups and point-in-time recovery must be selected and
rehearsed. Database recovery does not cover Cloudinary or external-provider state. See the
[database backup/restore runbook](runbooks/database-backup-restore.md).

## Cloudinary metadata

`cloudinary_assets` stores stable provider identifiers and metadata, not delivery URLs. Assets must
use `authenticated` delivery, overwrite is disabled, and each `document_version` owns one asset.
The application authorizes every access before generating a short-lived signed URL. New document
versions store their upload-intent expiry and remain quarantined until the exact reserved provider
identity, declared byte count, and upload response signature are verified. Completion creates one
tenant-scoped `document.scan` job using the document-version ID as its idempotency key. Scan results
are append-only per scanner/version; only a clean result marks the asset verified and permits the
document version to enter parsing.

Immutable parser/OCR attempts live in `document_parses`; ordered source output lives in
`document_pages`. Each attempt has a tenant-and-version-scoped result key, monotonic attempt
version, parser identity, native/OCR/hybrid kind, outcome, page count, and canonical SHA-256 content
digest. Page rows retain source label, text, dimensions, OCR confidence, and structured table data.
Composite foreign keys prevent pages from being attached to a parse from another tenant or
document version. Failed attempts remain evidence and permit a later attempt; only a completed
attempt moves the document version from `parsing` to `parsed`.

`extractions` binds a schema/version and canonical content digest to one completed parse digest and
one `analysis_runs` record. `extracted_fields` distinguishes proposed, missing, ambiguous,
conflicting, verified, and rejected states. `evidence_anchors` uses tenant-qualified composite keys
to ensure each field cites a page from the same document version and parse. `field_reviews` is an
append-only correction/decision history containing previous and reviewed values, actor, reason,
and time. The mutable extraction header has an optimistic review revision; completed extraction
fields and review history are not overwritten.
