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

Every HTTP response includes `X-Request-ID`. A caller-supplied value is echoed only when it is a
bounded ASCII token; otherwise the API generates a UUID. Responses also use
`Cache-Control: no-store` and defensive browser headers. Browser access is limited to exact CORS
origins, and requests with an untrusted `Host` header are rejected before route handling.

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
| `GET /health/ready` | `200` when PostgreSQL is reachable; bounded `503` on timeout/unavailability |

Readiness failures use a safe `checks.database.status` value of `timeout` or `unavailable` and do
not return provider exception text or connection details. Liveness intentionally performs no
dependency checks, preventing a database outage from turning into a process restart loop.

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
| `POST /api/v1/rfq-invitations/{id}/submissions` | `sourcing.submissions.manage` | Record an immutable, deadline-checked quote and its document-version attachments only when its explicit `rfq_revision_id` is current |
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
| `GET /api/v1/documents/versions/{version_id}/download` | `documents.read` | Issue an audited short-lived URL for a tenant-owned clean, verified asset |

The intake API currently supports PDF, XLSX, DOCX, JPEG, and PNG with a configurable byte limit
(25 MiB by default). Filenames must be basenames, hashes are lowercase SHA-256 declarations, and
upload intents expire after ten minutes by default. Assets remain quarantined and unavailable to
parsers until an authorized clean scan result advances the version to `parsing` and queues one
parse job. Parser results use a stable `result_key`: replaying the same content returns the existing
result, while reusing the key with changed content is a conflict. Successful native, OCR, or hybrid
results require consecutive pages and advance the version to `parsed`; failed attempts remain
immutable while the version stays recoverable in `parsing`. User downloads recheck tenant access
and safe asset state before issuing a short-lived authenticated URL. The scan and parser
worker/provider integrations, server-side byte/hash reconciliation, model-driven extraction, and
parser-worker downloads remain P4 work.

## Implemented extraction and review endpoints

| Endpoint | Permission | Behavior |
|---|---|---|
| `POST /api/v1/document-versions/{id}/extractions` | `documents.process` | Idempotently record schema-validated proposed fields bound to a completed parse and evidence pages |
| `GET /api/v1/extractions/{id}` | `documents.read` | Return fields, evidence anchors, review history, digests, and workflow state |
| `POST /api/v1/extractions/{id}/fields/{field_id}/review` | `documents.review` | Verify, correct, or reject one field using the expected extraction revision |
| `POST /api/v1/extractions/{id}/finalize` | `documents.review` | Complete review only when every critical field is verified and all fields are resolved |

Extraction output can propose `proposed`, `missing`, `ambiguous`, or `conflicting`; it cannot mark
itself verified. Every non-missing value requires an anchor to a page from the bound parse. Result
keys and canonical digests make worker replay idempotent, and optimistic revisions protect review
updates. Corrections preserve prior status/value and reviewer/reason. Finalization moves the
document version to `reviewed` and completes the bound analysis run. LangChain/model execution,
production PostgreSQL checkpoint wiring, and an extraction worker remain P4 integration work.

## Implemented evaluation endpoints

| Endpoint | Permission | Behavior |
|---|---|---|
| `POST /api/v1/rfqs/{id}/evaluations` | `evaluations.run` | Validate a complete requirement matrix and create an immutable deterministic comparison snapshot |
| `GET /api/v1/evaluations/{id}` | `evaluations.read` | Return evaluated offers, requirement outcomes, eligibility, landed costs, and scores |
| `POST /api/v1/evaluations/{id}/analysis-runs` | `evaluations.run` | Idempotently queue a Gemini-grounded comparison run |
| `GET /api/v1/evaluation-analysis-runs/{id}` | `evaluations.read` | Return durable run status, validated narrative, citations, and failure metadata |
| `POST /api/v1/evaluation-analysis-runs/{id}/resume` | `evaluations.run` | Resume a digest-bound PostgreSQL-checkpointed thread after review |

Evaluation requires every current submitted quote version and exactly one
`pass`/`fail`/`unknown`/`not_applicable` outcome per RFQ requirement. Mandatory failures make an
offer ineligible; mandatory unknown or not-applicable outcomes block it. Only eligible offers
receive scores. Landed cost is the exact decimal sum of line quantity × unit price, tax, and
freight. Price and preferred-requirement weights must total exactly one. The source versions,
quote digests, matrix, arithmetic results, scoring policy, and SHA-256 digest are stored as an
immutable evaluation version. A check may cite reviewed evidence anchors, but every citation must
resolve through the assessed quote's immutable document attachment to a verified field in a
completed extraction. Responses include those anchor IDs and a deterministic summary of counts,
the leading eligible submission, and the cited evidence set.

Requirement outcomes and rationales remain controlled reviewer inputs. Gemini receives the
immutable deterministic snapshot plus only tenant-authorized verified evidence. Native structured
output is application-validated, and every generated claim must cite a supplied anchor; supplier
narratives cannot cite another submission's evidence. Celery/RabbitMQ executes the graph with
bounded retry and PostgreSQL checkpoints. Formal waivers and independent-review disagreement
handling remain follow-on work.

## Implemented allocation and award endpoints

| Endpoint | Permission | Behavior |
|---|---|---|
| `POST /api/v1/evaluations/{id}/allocation-scenarios` | `allocations.run` | Solve and independently validate an immutable constrained-allocation scenario |
| `GET /api/v1/evaluations/{id}/allocation-scenarios` | `evaluations.read` | Compare scenario status, objective, bound/gap, constraints, conflicts, and allocations |
| `POST /api/v1/allocation-scenarios/{id}/awards` | `awards.write` | Build an immutable recommendation dossier bound to an active approval policy |
| `GET /api/v1/awards/{id}` | `awards.read` | Read the dossier, exact snapshot, status, quorum, and decisions |
| `POST /api/v1/awards/{id}/submit` | `awards.write` | Submit the exact digest for human approval after revalidating its sources |
| `POST /api/v1/awards/{id}/approve` | `awards.approve` | Add one quorum decision; only the exact current snapshot can become approved |
| `POST /api/v1/awards/{id}/reject` | `awards.approve` | Reject the exact pending recommendation with an auditable decision |

CP-SAT uses scaled integers for quantities and money, a deterministic single-worker search, and a
30-second maximum caller-configurable time budget. A feasible timeout is labeled `feasible`, never
`optimal`. Infeasible scenarios persist diagnostics rather than silently weakening constraints.
Awards can originate only from independently validated feasible scenarios. Approval policy rules
and versions are copied into the dossier; expired quotes, changed policies, stale grounded
analyses, and other material source changes persist a `stale` award rather than accepting another
decision.

## Implemented order operations endpoints

| Endpoint | Permission | Behavior |
|---|---|---|
| `POST /api/v1/awards/{id}/purchase-orders` | `orders.write` | Prepare one supplier PO from an approved, current award snapshot |
| `GET /api/v1/purchase-orders/{id}` | `orders.read` | Return the current PO and immutable version snapshot |
| `POST /api/v1/purchase-orders/{id}/amend` | `orders.write` | Create a new version; commercial changes require authorization |
| `POST /api/v1/purchase-orders/{id}/authorize-amendment` | `orders.approve` | Independently authorize a material amendment |
| `POST /api/v1/purchase-orders/{id}/issue` | `orders.issue` | Issue the exact current digest |
| `POST /api/v1/purchase-orders/{id}/acknowledge` | `orders.acknowledge` | Record acceptance, rejection, or proposed changes without changing terms |
| `POST /api/v1/purchase-orders/{id}/receipts` | `orders.receive` | Record accepted/rejected quantities with over-receipt protection |
| `POST /api/v1/receipt-lines/{id}/returns` | `orders.receive` | Record a return up to accepted quantity |
| `POST /api/v1/purchase-orders/{id}/invoices` | `invoices.write` | Capture invoice lines and flag normalized duplicate numbers |
| `GET /api/v1/invoices/{id}` | `invoices.read` | Return invoice lines and workflow version |
| `POST /api/v1/invoices/{id}/match` | `invoices.match` | Run deterministic two-way or three-way matching |
| `POST /api/v1/match-exceptions/{id}/resolve` | `invoices.match` | Record an auditable exception resolution |
| `POST /api/v1/invoices/{id}/approve-for-export` | `invoices.approve` | Approve a clean or fully resolved match |
| `POST /api/v1/invoices/{id}/accounting-exports` | `accounting.export` | Export once using a stable external reference |
| `POST /api/v1/accounting-exports/{id}/retry` | `accounting.export` | Reconcile by stable reference before retry |
| `POST /api/v1/accounting-exports/{id}/reconcile` | `accounting.reconcile` | Record reconciled or mismatch status |

PO creation revalidates the award's evaluation, allocation, policy, selected quote, and supplier
inputs. Material quantity or monetary amendments require independent renewed authorization.
Receipts count accepted plus rejected delivery against the ordered ceiling, while fulfillment uses
accepted quantity net of returns. Matching snapshots the PO revision, receipt basis, prior matched
billing, tolerances, and invoice inputs. Quantity, price, currency, tax, freight, total, and
duplicate failures create durable exception rows. Accounting export uses one row per invoice, a
stable `PX-INVOICE-{invoice_id}` reference, and a payload digest for retry safety.

## Events

Business state and an `outbox_events` row are committed in one transaction. Consumers assume
at-least-once delivery and deduplicate by event ID. The event envelope contains organization,
aggregate/version, event/schema type, actor, time, correlation, causation, and a minimal payload.

Implemented event families include `purchase_order.*`, `delivery_receipt.*`, `delivery_return.*`,
`invoice.*`, and `accounting_export.*`. Every consequential P7 mutation writes its audit and outbox
records in the same database transaction.
