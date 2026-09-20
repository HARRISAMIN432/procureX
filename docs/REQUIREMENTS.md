# Requirements

## Requirement groups

Stable requirement identifiers are defined in [ROADMAP.md](ROADMAP.md), Section 4.

| Prefix | Area | Initial release emphasis |
|---|---|---|
| ORG | Organization, identity, policy, lifecycle | Tenant isolation, membership, settings, audit |
| REQ | Requisitions and budgets | Typed lines, approval, safe budget reservation |
| SUP | Supplier master and qualification | Buyer-scoped relationship and verification |
| RFQ | Sourcing and supplier submissions | Immutable RFQs and quote versions |
| DOC | Document processing and evidence | Safe intake, Cloudinary, extraction provenance |
| EVAL | Compliance, comparison, and risk | Deterministic scoring and grounded summaries |
| AWD / PO | Award and purchase orders | Snapshot approval and idempotent issuance |
| OPS | Receipt, invoice, contract, and monitoring | Three-way matching and exception workflows |
| REP | Reporting and collaboration | Permission-aware reporting and evidence exports |

## Foundation acceptance criteria

**Current status:** configuration, schema, local identity bootstrap, RBAC context, organization
reads, versioned settings APIs, and the REQ-01/REQ-02 draft-to-submission requisition slice are
implemented. The initial REQ-03/REQ-04 approval-policy, quorum, rejection, budget-ledger, and atomic
reservation slice is also implemented. The initial SUP-01 through SUP-03 buyer-scoped supplier
profile, contact, qualification, certificate, approval, and suspension slice is implemented;
supplier self-service, invitations, duplicate suggestions/merge, reminders, and award eligibility
enforcement remain later work. Live PostgreSQL migration and concurrency/cross-tenant integration
tests remain pending until a database service is available. The initial RFQ-01 through RFQ-04 and
RFQ-06 sourcing slice now covers versioned publication/amendment, approved-supplier invitations,
deadline-controlled immutable quote versions, cancellation/closure, and clarification records.
Invitation acknowledgement and no-bid transitions are now implemented in the controlled intake
API with RFQ version/deadline checks and a retained decline reason. Direct supplier authentication,
attachment intake, notification delivery, and full portal isolation remain incomplete.

The initial P4/DOC-01 and DOC-02 intake slice now provides constrained PDF/XLSX/DOCX/JPEG/PNG
upload intents, immutable authenticated Cloudinary identities, provider-response verification,
quarantine state, idempotent scan dispatch, trusted scan-result recording, and tenant document
reads. The follow-on P4 slice adds idempotent native/OCR/hybrid result ingestion, immutable parser
attempts, canonical result digests, and ordered page/text/table sources. Actual scanner/parser
execution, server-side byte/hash verification, and model-driven structured extraction remain
incomplete. Tenant-authorized user downloads now issue audited, short-lived Cloudinary URLs only
for post-scan versions backed by verified assets.

The structured extraction/review slice now persists schema-bound proposed fields, same-parse page
anchors, missing/ambiguous/conflicting states, optimistic human verification/correction history,
and a critical-field finalization gate. It also provides a tested `document_analysis_graph`
interrupt/resume contract that rejects stale source digests. LangChain/model worker execution,
durable PostgreSQL graph invocation/checkpoint integration, automated arithmetic validation, and
the evidence-viewer UI remain incomplete.

The P5/EVAL work now implements complete requirement matrices over closed RFQs and current submitted
quote versions, four-state requirement outcomes, mandatory-unknown blocking, exact decimal landed
cost, deterministic weighted comparison and summaries, immutable versioned snapshots/digests,
tenant constraints, permissions, and audit/outbox records. Quote versions retain immutable
document-version attachments; a check citation is accepted only when it resolves to a verified
field in a completed extraction of an attached document. A tested `evaluation_graph` contract
validates the evidence gate, interrupts on unresolved findings, and rejects stale-digest resumes.
Gemini 3.1 grounded narratives, authorized evidence retrieval, persisted analysis/model lifecycle,
Celery worker execution, and PostgreSQL LangGraph checkpoints are implemented. Formal waiver and
independent-review workflows, risk signals, allocation optimization, and award integration remain
outside this P5 slice.

The P6/AWD slice implements deterministic OR-Tools CP-SAT allocation scenarios over eligible,
current quotes and approved suppliers. It supports capacity, minimum quantity, split-award,
supplier-count, fixed-cost, and budget constraints; preserves honest optimal/feasible/infeasible
status, bounds/gaps and actionable conflicts; and independently validates every feasible result.
Immutable recommendation dossiers bind the evaluation, scenario, submissions, allocation, and
approval-policy version. Human decisions require separate permission, enforce quorum and optional
self-approval prohibition, and mark the recommendation stale when selected submissions, supplier
eligibility, evaluation, or allocation sources change.

The P7 order-operations slice implements idempotent PO creation from current approved awards,
versioned amendments with renewed authorization for material changes, issue and supplier-response
recording, partial receipts and returns, duplicate-aware invoice capture, two- and three-way
matching with blocking exception resolution, and idempotent sandbox accounting export and
reconciliation. Order, invoice, and accounting permissions are included in new-organization
bootstrap; rejected or change-requested POs cannot proceed to receipt or invoice processing.

The first P8 stabilization slice adds fail-closed deployed HTTP-edge configuration, exact trusted
host and CORS allowlists, HTTPS-only deployed browser origins, request correlation IDs, defensive
response headers, HSTS in staging/production, and disabled production API documentation routes.
Database readiness is now bounded by a configurable timeout and returns a safe structured `503`
without leaking connection errors; a recovery/drill runbook distinguishes traffic draining from
process restart decisions.

The current backend foundation must provide:

- validated environment configuration with no committed secrets;
- async PostgreSQL access and repeatable Alembic migrations;
- organizations, users, memberships, roles, and permissions;
- versioned organization settings;
- immutable document versions and Cloudinary asset references;
- document quarantine and malware-scan state;
- LangGraph analysis-run and model-invocation metadata;
- durable jobs, outbox events, and append-only audit events;
- tenant row-level security plus application tenant context; and
- tests that detect missing tables and isolation controls.

## Definition of done

A requirement is complete only when normal and exceptional paths work, permissions are enforced,
migrations and tests exist, audit/telemetry are present, documentation is current, and its
acceptance evidence is recorded. A mock, manual database edit, or unimplemented UI control does
not satisfy a requirement.
