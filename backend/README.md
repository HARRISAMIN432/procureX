# ProcureX backend

Initial FastAPI/PostgreSQL foundation for ProcureX. It includes environment validation,
async SQLAlchemy models, Alembic, Cloudinary asset metadata, LangGraph run metadata,
tenant-aware database helpers, durable jobs/outbox events, and audit records.

Cloudinary upload options are generated server-side and enforce `authenticated` delivery,
`raw` resources, immutable provider IDs, and overwrite protection.

## Local setup

```bash
cp .env.example .env
docker compose up -d postgres rabbitmq redis
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Run checks with:

```bash
uv run ruff check .
uv run pytest
```

Application transactions that access tenant-owned tables must use
`tenant_transaction(organization_id)` or set the equivalent transaction-local PostgreSQL
context. Never accept the organization ID directly from an unauthenticated request body.

## Local identity bootstrap

The temporary development identity mechanism is available only in `local` and `test`. Create the
first organization with:

```bash
curl -X POST http://localhost:8000/api/v1/organizations/dev-bootstrap \
  -H 'Content-Type: application/json' \
  -H 'X-Dev-Bootstrap-Key: local-development-only' \
  -d '{
    "organization_name": "Acme Limited",
    "organization_slug": "acme-limited",
    "admin_email": "admin@example.com",
    "admin_display_name": "Admin User"
  }'
```

Use the returned `organization_id` and `user_id` as `X-Organization-ID` and `X-User-ID` headers
for local authenticated requests. Staging and production configuration rejects this mechanism and
requires OIDC mode.

Implemented organization endpoints are documented in
[`../docs/API.md`](../docs/API.md#implemented-identity-endpoints).

The first requisition slice is also available under `/api/v1/requisitions`, with exact decimal
validation, optimistic versions, permission checks, immutable submission snapshots, audit events,
and outbox events. See [the API reference](../docs/API.md#implemented-requisition-endpoints).

Approval policies, quorum decisions, budgets, append-only ledger balances, and atomic reservation
are available through the approval/budget endpoints documented in
[`../docs/API.md`](../docs/API.md#implemented-approval-and-budget-endpoints).

Buyer-scoped supplier profiles, contacts, qualifications, certificates, approval, and suspension
are available under `/api/v1/suppliers`. The endpoint and permission matrix is documented in
[`../docs/API.md`](../docs/API.md#implemented-supplier-endpoints).

The first sourcing slice is available under `/api/v1/rfqs` and
`/api/v1/rfq-invitations`: versioned publication/amendment, approved-supplier invitations,
deadline-controlled immutable quote versions, acknowledgement/no-bid responses, stale-revision
rejection, and clarifications. See
[`../docs/API.md`](../docs/API.md#implemented-sourcing-endpoints).
