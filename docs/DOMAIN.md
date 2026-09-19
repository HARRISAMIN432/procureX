# Domain model

## Bounded contexts

| Context | Responsibilities |
|---|---|
| Identity | Organization, user, membership, role, permission, delegation |
| Procurement | Requisition, lines, requirements, budgets, approvals |
| Sourcing | RFQ versions, invitations, clarifications, quote versions |
| Suppliers | Supplier identity, buyer relationship, qualification, performance |
| Documents | Immutable files, scans, extraction, evidence, corrections |
| Intelligence | Analysis runs, requirement checks, risk signals, summaries |
| Optimization | Scenarios, constraints, solver runs, allocations |
| Governance | Policies, decisions, exceptions, audit events |
| Operations | Awards, POs, amendments, receipts, returns, claims |
| Finance | Invoices, matches, credits, disputes, accounting exports |

## Core invariants

- Every tenant-owned row carries `organization_id`.
- Cross-tenant references are prevented with composite constraints where applicable.
- Money uses decimal arithmetic with an explicit currency and rounding policy.
- Quantity includes unit and allowed precision.
- Published RFQs, submitted quotes, approved awards, and issued POs are immutable versions.
- Evidence anchors point to immutable document versions and source coordinates.
- Approvals bind to a content/version digest and policy version.
- Consequential commands use tenant-scoped idempotency keys.
- Unknown mandatory requirements block eligibility until resolved or formally waived.
- AI output is proposed evidence, never business authorization.

## Identity rule

A user is global and can join multiple organizations. A membership is tenant-specific and receives
one or more tenant roles. Every request selects one authenticated membership context; request body
fields cannot override it.

## Document rule

A logical document can have multiple immutable versions. Each version has an original byte hash,
one authenticated Cloudinary asset, scan results, and derived evidence. Corrections create new
records and never overwrite source bytes or prior review history.

