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

## Events

Business state and an `outbox_events` row are committed in one transaction. Consumers assume
at-least-once delivery and deduplicate by event ID. The event envelope contains organization,
aggregate/version, event/schema type, actor, time, correlation, causation, and a minimal payload.

The first event families are `document.*`, `analysis.*`, followed by the procurement events listed
in [ROADMAP.md](ROADMAP.md), Section 9.
