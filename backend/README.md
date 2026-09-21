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

Browser and proxy boundaries are explicit. Configure `PROCUREX_ALLOWED_HOSTS` and
`PROCUREX_CORS_ALLOWED_ORIGINS` as JSON arrays. Staging and production reject wildcard/empty
values, non-HTTPS browser origins, debug mode, and SQL statement logging. The API returns a safe
`X-Request-ID` and defensive browser headers on every response; production also disables `/docs`,
`/redoc`, and `/openapi.json`. TLS termination and HTTP-to-HTTPS redirects remain edge concerns.

`/health/ready` checks PostgreSQL within `PROCUREX_READINESS_TIMEOUT_SECONDS` and returns a safe
structured `503` when the dependency fails or stalls. `/health/live` performs no dependency check.
See the [database readiness runbook](../docs/runbooks/database-readiness.md) before wiring probes.

Every request returns `Server-Timing` and writes safe request-ID-correlated completion telemetry.
Requests over `PROCUREX_SLOW_REQUEST_THRESHOLD_MS` and all server errors are warnings. See the
[API latency/error runbook](../docs/runbooks/api-latency-and-errors.md) for triage and measurement.

Non-production database recovery drills use `python -m app.admin.database_backup`. The tool creates
a private PostgreSQL custom archive with an integrity manifest and restores only into an explicitly
confirmed empty target. Read the [backup/restore runbook](../docs/runbooks/database-backup-restore.md)
before use; production and Cloudinary recovery require separate provider procedures.

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

For deployed OIDC, configure `PROCUREX_OIDC_ISSUER`, `PROCUREX_OIDC_AUDIENCE`, and the provider's
HTTPS `PROCUREX_OIDC_JWKS_URL`. Bearer subjects must hold an active membership in the selected
`X-Organization-ID`. Administrators can invite members and assign roles through
`/api/v1/organizations/current/members`; a first login accepts an invite only from a
provider-verified matching email. Optional self-service organization signup is guarded by
`PROCUREX_ALLOW_SELF_SERVICE_ORGANIZATION_SIGNUP`. Only configured asymmetric signature algorithms
are accepted.

The repository root contains a Render Blueprint for a no-cost demonstration deployment. Read
[`../docs/DEPLOY_RENDER.md`](../docs/DEPLOY_RENDER.md) before using it: Render's free database,
in-memory task mode, cold starts, and lack of a free worker make it unsuitable for customer data or
a commercial production SLA.

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

The first P4 document-intake slice is available under `/api/v1/documents`: constrained expiring
upload intents, authenticated/raw Cloudinary response verification, immutable asset registration,
idempotent scan dispatch, and scan-gated parsing/rejection. See the
[document API reference](../docs/API.md#implemented-document-intake-endpoints).

Clean, verified document versions can be downloaded through a tenant-authorized endpoint that
returns an audited, short-lived authenticated Cloudinary URL. Quarantined and unsafe asset states
fail closed.

Upload completion dispatches the scan job to `documents.security`. The worker independently
downloads the signed asset without redirects, verifies its exact byte count and SHA-256, and then
runs ClamAV under a timeout. Integrity and scanner failures remain quarantined and retry at most
three total attempts; only explicit clean/infected verdicts change asset state. Run it with a
current ClamAV signature database mounted or installed in the worker image:

```bash
uv run celery -A app.workers.celery_app:celery_app worker \
  --queues documents.security --loglevel INFO
```

Clean scans then dispatch an idempotent parse job to `documents.parsing`. The parser runs in a
separate process with seccomp-denied network sockets plus CPU, memory, file-descriptor, process,
timeout, archive-expansion, page, worksheet, and output limits. It performs native PDF/DOCX/XLSX
extraction and Tesseract OCR for images or image-only PDF pages, and records replay-safe ordered
page text and tables. Run both document queues with:

```bash
uv run celery -A app.workers.celery_app:celery_app worker \
  --queues documents.security,documents.parsing --loglevel INFO
```

Successful parsing advances the immutable version to `parsed`. Structured extraction execution
remains subsequent integration work.

Structured extraction results can now be recorded against completed parses with page-level evidence
anchors. Human reviewers verify/correct/reject fields under optimistic revisions; critical fields
must be verified before finalization. The tested `document_analysis_graph` contract pauses for
review and rejects stale source-digest resumes. Model execution and production checkpoint wiring
remain integration work.

The first P5 evaluation slice is available through `/api/v1/rfqs/{id}/evaluations` and
`/api/v1/evaluations/{id}`. It builds a complete four-state requirement matrix, blocks unresolved
mandatory criteria, calculates exact landed costs and deterministic weighted scores, and preserves
each comparison as an immutable digest-bearing version. Quote submissions can bind immutable
document versions; evaluation citations must resolve to verified fields from completed extractions
of those documents. A Celery-backed `evaluation_graph` now retrieves only authorized verified
evidence, generates a structured citation-grounded comparison with `gemini-3.1-pro-preview`,
validates every citation, persists invocation/run metadata, checkpoints in PostgreSQL, pauses on
unresolved findings, and rejects stale resumes. Requirement outcomes and all commercial arithmetic
remain reviewer/deterministic inputs.

Configure `PROCUREX_GEMINI_API_KEY`, then run the evaluation worker with:

```bash
uv run celery -A app.workers.celery_app:celery_app worker \
  --queues ai.evaluations --loglevel INFO
```

The worker initializes the LangGraph checkpoint schema idempotently using
`PROCUREX_LANGGRAPH_CHECKPOINT_DATABASE_URL`. Start a run through
`POST /api/v1/evaluations/{evaluation_id}/analysis-runs` and poll it through
`GET /api/v1/evaluation-analysis-runs/{analysis_run_id}`. If its status is `awaiting_review`, resume
it with the source digest returned on the run.

P6 allocation and award APIs use OR-Tools CP-SAT with integer-scaled quantities and money. Scenarios
preserve constraints, solver status, objective/bound/gap, infeasibility diagnostics, independent
constraint checks, and immutable digests. Validated feasible scenarios can become recommendation
dossiers governed by the existing versioned approval policies. Quorum decisions are append-only,
self-approval policy is enforced, and changed evaluation, allocation, grounded analysis, approval
policy, selected quote, or supplier inputs mark an award stale before authorization.

P7 order operations are available through purchase-order, receipt, invoice, match, and accounting-
export endpoints. POs originate only from a current approved award, retain immutable revisions, and
require independent renewed authorization for material amendments. Cumulative receipt and return
rules protect quantities. Deterministic two-/three-way matching records duplicate, quantity, price,
tax, freight, currency, and total exceptions with explicit tolerances. The accounting sandbox uses
stable external references and payload digests for idempotent retry and reconciliation. See the
[order operations API](../docs/API.md#implemented-order-operations-endpoints).

Run the PostgreSQL P7 integration scenario against a migrated test database with:

```bash
PROCUREX_TEST_DATABASE_URL=postgresql+asyncpg://procurex:procurex@localhost:5432/procurex \
  uv run pytest tests/test_order_operations_integration.py
```

Run the deterministic allocation benchmark with:

```bash
uv run python -m app.admin.performance_benchmark \
  --items 100 --suppliers 50 --repetitions 5 --maximum-p95-ms 30000
```

The repository CI migrates a PostgreSQL 17 service as the schema owner, grants a separate
`NOSUPERUSER NOBYPASSRLS` runtime role, runs the complete suite (including the normally skipped
integration scenario), audits locked dependencies, and builds the non-root production container.
Hosted CI success is required evidence; the workflow file alone is not a passing release gate.
