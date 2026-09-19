# API conventions

## HTTP contract

- Base path: `/api/v1`.
- JSON request and response models are typed with Pydantic.
- OpenAPI is the source for generated clients.
- Tenant context comes from the authenticated membership.
- Errors have a stable code, message, request ID, and optional safe field details.
- Collection endpoints define pagination, filters, and stable sort order.
- Updates use expected versions or ETags.
- Long work returns `202 Accepted` with an authorized job resource.

Consequential commands use explicit endpoints such as:

```text
POST /requisitions/{id}/submit
POST /awards/{id}/submit
POST /purchase-orders/{id}/issue
POST /analysis-runs/{id}/resume
```

Creates and consequential commands require an idempotency key. Reusing a key with a different
payload is a conflict.

## Health endpoints

| Endpoint | Meaning |
|---|---|
| `GET /health/live` | Process is running; no dependency check |
| `GET /health/ready` | Required database dependency is reachable |

## Implemented identity endpoints

| Endpoint | Permission / restriction |
|---|---|
| `POST /api/v1/organizations/dev-bootstrap` | Local/test only; `X-Dev-Bootstrap-Key` required |
| `GET /api/v1/organizations/current` | `organization.read` |
| `GET /api/v1/organizations/current/membership` | `organization.read` |
| `GET /api/v1/organizations/current/settings` | `organization.settings.read` |
| `PUT /api/v1/organizations/current/settings` | `organization.settings.write` |

Until an OIDC provider is selected, local requests identify their development principal with
`X-Organization-ID` and `X-User-ID`. Configuration rejects this auth mode in staging and
production; the headers are not a production authentication mechanism.

## Implemented requisition endpoints

| Endpoint | Permission | Behavior |
|---|---|---|
| `POST /api/v1/requisitions` | `requisitions.write` | Create a draft with lines and structured requirements |
| `GET /api/v1/requisitions` | `requisitions.read` | Return a stable paginated tenant list |
| `GET /api/v1/requisitions/{id}` | `requisitions.read` | Return the aggregate with lines and requirements |
| `PUT /api/v1/requisitions/{id}` | `requisitions.write` | Replace editable draft content using `expected_version` |
| `POST /api/v1/requisitions/{id}/submit` | `requisitions.submit` | Validate and snapshot the submitted version |
| `POST /api/v1/requisitions/{id}/cancel` | `requisitions.cancel` | Cancel an allowed state with reason and expected version |

Draft writes accept exact decimal quantities/prices, ISO currency, optional delivery date/location,
JSON specifications, and mandatory/preferred requirements. Requirement inputs may reference a line
number; database constraints preserve the same-tenant, same-requisition relationship. Submission
requires at least one line and confirmation of every proposed requirement.

## Implemented approval and budget endpoints

| Endpoint | Permission | Behavior |
|---|---|---|
| `POST /api/v1/budgets` | `budgets.manage` | Create a dated currency budget and initial ledger allocation |
| `GET /api/v1/budgets` | `budgets.read` | Return balances derived from ledger deltas |
| `POST /api/v1/approval-policies` | `approvals.policies.manage` | Create a new effective policy version |
| `POST /api/v1/requisitions/{id}/approval-requests` | `approvals.request` | Bind submitted snapshot, policy, budget, amount, and quorum |
| `GET /api/v1/approval-requests/{id}` | `approvals.read` | Return the request and recorded decisions |
| `POST /api/v1/approval-requests/{id}/approve` | `approvals.decide`, `budgets.reserve` | Record approval and reserve funds when quorum is reached |
| `POST /api/v1/approval-requests/{id}/reject` | `approvals.decide` | Reject the request and requisition |

The request stores the exact requisition version/digest and a policy snapshot. An approver can
decide once. Policies can require multiple distinct approvers and prohibit requester
self-approval. Final approval locks the budget before checking and reserving available funds.

## Implemented supplier endpoints

| Endpoint | Permission | Behavior |
|---|---|---|
| `POST /api/v1/suppliers` | `suppliers.write` | Create a buyer-scoped pending supplier and contacts |
| `GET /api/v1/suppliers` | `suppliers.read` | Return a stable paginated tenant directory |
| `GET /api/v1/suppliers/{id}` | `suppliers.read` | Return profile, contacts, qualifications, and certificates |
| `PUT /api/v1/suppliers/{id}` | `suppliers.write` | Replace an editable profile using `expected_version`; approved profiles return to pending review |
| `POST /api/v1/suppliers/{id}/qualifications` | `suppliers.qualify` | Add a pending category qualification |
| `POST /api/v1/suppliers/{id}/qualifications/{qualification_id}/decision` | `suppliers.qualify` | Record a qualified or unqualified assessment |
| `POST /api/v1/suppliers/{id}/certificates` | `suppliers.qualify` | Register certificate metadata and an optional immutable document version |
| `POST /api/v1/suppliers/{id}/certificates/{certificate_id}/review` | `suppliers.qualify` | Verify or reject a certificate |
| `POST /api/v1/suppliers/{id}/approve` | `suppliers.approve` | Approve a version with at least one current qualification |
| `POST /api/v1/suppliers/{id}/suspend` | `suppliers.approve` | Suspend an approved supplier with a reason |

Supplier registration and certificate identities are unique inside the buyer organization.
Mutations lock the supplier aggregate and emit audit and outbox records. Sensitive payment and
banking fields are intentionally excluded until an independently verified dual-review workflow is
implemented.

## Implemented sourcing endpoints

| Endpoint | Permission | Behavior |
|---|---|---|
| `POST /api/v1/rfqs` | `sourcing.write` | Create a draft from an approved requisition and copy its controlled requirements |
| `GET /api/v1/rfqs` | `sourcing.read` | Return the tenant RFQ directory with stable pagination |
| `GET /api/v1/rfqs/{id}` | `sourcing.read` | Return items, requirements, invitations, quote versions, and clarifications |
| `PUT /api/v1/rfqs/{id}` | `sourcing.write` | Replace draft header/terms using `expected_version` |
| `POST /api/v1/rfqs/{id}/invitations` | `sourcing.invite` | Add approved suppliers before publication |
| `POST /api/v1/rfq-invitations/{id}/acknowledge` | `sourcing.submissions.manage` | Acknowledge an open invitation using the expected RFQ version |
| `POST /api/v1/rfq-invitations/{id}/no-bid` | `sourcing.submissions.manage` | Decline before the deadline and retain the supplied reason |
| `POST /api/v1/rfqs/{id}/publish` | `sourcing.publish` | Create immutable publication 1 and move the requisition to sourcing |
| `POST /api/v1/rfqs/{id}/amend` | `sourcing.publish` | Create a new immutable publication with a reason and future deadline |
| `POST /api/v1/rfqs/{id}/close` | `sourcing.publish` | Close after the server-side deadline |
| `POST /api/v1/rfqs/{id}/cancel` | `sourcing.publish` | Cancel an open/draft RFQ with a reason |
| `POST /api/v1/rfq-invitations/{id}/submissions` | `sourcing.submissions.manage` | Record an immutable, deadline-checked quote only when its explicit `rfq_revision_id` is current |
| `POST /api/v1/quote-submissions/{id}/withdraw` | `sourcing.submissions.manage` | Withdraw only the latest quote before the deadline using the expected RFQ version |
| `POST /api/v1/rfqs/{id}/clarifications` | `sourcing.clarifications.write` | Create a shared or invitation-private question before the deadline |
| `POST /api/v1/rfqs/{id}/clarifications/{clarification_id}/answer` | `sourcing.clarifications.write` | Answer an open clarification and preserve its visibility |

The current invitation-response and submission endpoints are controlled buyer-side intake APIs.
Acknowledgement and no-bid transitions enforce RFQ version, state, and server deadline checks and
emit audit/outbox evidence. Quote creates explicitly identify the revision the supplier answered;
a concurrent amendment makes the request stale instead of silently rebinding it. Direct supplier
portal authentication and object filtering, attachment intake, outbound notifications, and
idempotency-key middleware remain P3 work and must land before external suppliers use the API.

## Implemented document intake endpoints

| Endpoint | Permission | Behavior |
|---|---|---|
| `POST /api/v1/documents/upload-intents` | `documents.write` | Validate metadata, create a quarantined immutable version, and return a short-lived signed Cloudinary upload request |
| `POST /api/v1/documents/{id}/versions/{version_id}/complete-upload` | `documents.write` | Verify the exact authenticated/raw provider response, register the asset, and enqueue scanning once |
| `POST /api/v1/documents/versions/{version_id}/scan-results` | `documents.scan` | Record a trusted scanner result and gate parsing/rejection |
| `POST /api/v1/documents/versions/{version_id}/parse-results` | `documents.process` | Idempotently record an immutable native/OCR/hybrid attempt with ordered pages and tables |
| `GET /api/v1/documents` | `documents.read` | List tenant documents with version, asset, and scan state |
| `GET /api/v1/documents/{id}` | `documents.read` | Return one tenant document and its immutable version history |

The intake API currently supports PDF, XLSX, DOCX, JPEG, and PNG with a configurable byte limit
(25 MiB by default). Filenames must be basenames, hashes are lowercase SHA-256 declarations, and
upload intents expire after ten minutes by default. Assets remain quarantined and unavailable to
parsers until an authorized clean scan result advances the version to `parsing` and queues one
parse job. Parser results use a stable `result_key`: replaying the same content returns the existing
result, while reusing the key with changed content is a conflict. Successful native, OCR, or hybrid
results require consecutive pages and advance the version to `parsed`; failed attempts remain
immutable while the version stays recoverable in `parsing`. The scan and parser worker/provider
integrations, server-side byte/hash reconciliation, extraction, review, and authorized download
URLs remain P4 work.

## Events

Business state and an `outbox_events` row are committed in one transaction. Consumers assume
at-least-once delivery and deduplicate by event ID. The event envelope contains organization,
aggregate/version, event/schema type, actor, time, correlation, causation, and a minimal payload.

The first event families are `document.*`, `analysis.*`, followed by the procurement events listed
in [ROADMAP.md](ROADMAP.md), Section 9.
