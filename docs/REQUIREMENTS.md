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
Direct supplier authentication, acknowledgements/no-bid, attachment intake, notification delivery,
and full portal isolation remain incomplete.

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
