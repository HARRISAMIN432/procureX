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
execution, server-side byte/hash verification, model-driven structured extraction, and document
download authorization remain incomplete.

The structured extraction/review slice now persists schema-bound proposed fields, same-parse page
anchors, missing/ambiguous/conflicting states, optimistic human verification/correction history,
and a critical-field finalization gate. It also provides a tested `document_analysis_graph`
interrupt/resume contract that rejects stale source digests. LangChain/model worker execution,
durable PostgreSQL graph invocation/checkpoint integration, automated arithmetic validation, the
evidence-viewer UI, and authorized document delivery remain incomplete.

The initial P5/EVAL slice now implements complete requirement matrices over closed RFQs and current
submitted quote versions, four-state requirement outcomes, mandatory-unknown blocking, exact
decimal landed cost, deterministic weighted comparison, immutable versioned snapshots/digests,
tenant constraints, permissions, and audit/outbox records. The matrix currently accepts controlled
reviewer outcomes and rationales. Direct links from checks to reviewed extraction evidence,
formal waiver workflow, risk signals, grounded narrative summaries, allocation optimization, and
award integration remain incomplete.

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
