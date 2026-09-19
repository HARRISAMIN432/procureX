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

Parser/OCR attempts are immutable children of a document version. Each attempt is content-digested
and owns ordered page/source records; retries create a new attempt unless they replay the same
result key and identical content. Parsed pages are evidence sources, not verified commercial
facts—structured fields and human review remain separate downstream records.

Extraction attempts bind to one immutable completed parse and schema version. A model or worker may
only propose field states; it cannot create verified values. Every present value cites a page, and
review actions preserve before/after values and reasons. An extraction is decision-eligible only
after every critical field is verified and every other field is verified or explicitly rejected.

## Evaluation rule

Evaluation runs only against a closed RFQ and includes every current submitted quote version in
the RFQ currency. Every offer must resolve the complete controlled requirement set. A mandatory `fail`
makes the offer ineligible; a mandatory `unknown` or `not_applicable` blocks it; only all-passing
mandatory checks are eligible. Preferred `not_applicable` checks are excluded from the preferred
ratio. Eligible offers are scored deterministically from exact landed cost and that ratio using
weights that total one; blocked and ineligible offers never receive a score.

Each run creates a new immutable version and digest rather than replacing an earlier comparison.
The current matrix is reviewer-supplied and rationale-bearing. Requirement-to-document evidence
links, formal waivers, risk signals, grounded summaries, and allocation optimization remain later
capabilities.
