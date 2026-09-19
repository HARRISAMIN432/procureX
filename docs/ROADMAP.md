# ProcureX — Product and Production Delivery Roadmap

**Version:** 1.2  
**Prepared:** 19 September 2026  
**Product:** Evidence-grounded procurement and supplier intelligence software  
**Status:** Implementation blueprint; capabilities and acceptance targets below are planned, not implemented or measured.

## 1. Product goal and scope

ProcureX helps organizations turn a purchasing requirement into a reviewed supplier award, purchase order, verified delivery, and reconciled invoice. It combines reliable business workflows, document intelligence, deterministic comparison, constrained allocation, and human authorization.

The central promise is: **every purchasing decision can be reconstructed from approved requirements, supplier submissions, evaluation rules, evidence, and authorized actions.**

This roadmap defines the complete intended product and the release gates required before real operational use. A roadmap cannot itself guarantee implementation completeness: each requirement must become a tracked ticket, implementation, test, and accepted operational capability.

### 1.1 Planning assumptions

- Initial customers: private-sector small and medium organizations purchasing goods through competitive quotations.
- Initial category: IT equipment; design line-item schemas so other goods categories can be added without rewriting the workflow.
- Initial deployment: multi-tenant SaaS in one region, with organization-level data isolation.
- Initial localization: English, PKR as the default currency, Asia/Karachi as the default display timezone; currency and timezone remain configurable.
- Initial workflow supports buyer organizations and invited suppliers. Public tendering and jurisdiction-specific statutory procurement are separate expansions.
- A suggested planning baseline is four contributors working approximately 15–20 hours each per week for 32 weeks. Availability and experience determine actual delivery dates.
- Real supplier data requires permission. Synthetic data must be labeled and cannot substantiate real-world business impact claims.
- Cloudinary is the selected managed file service behind a ProcureX-owned adapter. AI, OCR, email and exchange-rate providers remain replaceable adapters with documented data-handling terms.
- The Python AI application layer uses LangChain for provider-neutral model, embedding, retrieval, tool, prompt, and structured-output interfaces, and LangGraph for durable orchestration of multi-step AI workflows and human review interrupts.
- No compute cloud, model, business integration or budget has been selected by the user. Validate the Cloudinary plan, region, limits, backup behavior and data-handling terms in Phase 0 before committing infrastructure spend.

### 1.2 Release boundaries

| Release | Intended use | Required scope |
|---|---|---|
| R0: engineering foundation | Internal development | Identity, tenant boundaries, delivery pipeline, domain skeleton, observability |
| R1: FYP and controlled pilot candidate | Research evaluation and supervised trials | Requisition through RFQ, verified quotations, comparison, optimization, human award, PO, basic receipts and matching; all relevant safety gates |
| R2: production v1 | Supported customer operations | Complete operational workflows, returns/disputes, recovery drills, security review, onboarding, support, production connector and reconciliation |
| R3: enterprise expansion | Larger or more regulated customers | SSO/SCIM, advanced contracts, services procurement, catalogs, additional integrations and deployment options |

R1 is not automatically production-ready because the demo succeeds. Any unfinished R2 control remains an explicit limitation. Real purchasing must use a release that passes the controls applicable to its advertised scope.

### 1.3 Explicit product boundaries

ProcureX is the system of record for procurement workflow and decision evidence. The ERP/accounting system remains the authority for ledger entries and payment settlement when integrated. ProcureX records payment status and reconciliation; it does not initiate bank transfers in R1 or R2.

Full accounting, payroll, warehouse management, lending, autonomous purchasing, universal supplier scraping, and automatic legal certification are outside this roadmap. R3 contract features assist authorized reviewers; they do not declare a contract legally valid. Country-specific tax, retention, invoice, and procurement rules need qualified review before claiming support.

## 2. Users, permissions, and separation of duties

| Role | Capabilities | Restrictions |
|---|---|---|
| Organization administrator | Memberships, policies, integrations, organization settings | Cannot silently alter historical awards or impersonate an approver |
| Requester | Create requisitions, clarify requirements, view own requests | Cannot approve own restricted spending |
| Procurement officer | RFQs, invitations, quotation review, recommendation, PO preparation | Cannot bypass mandatory approval or modify supplier originals |
| Evaluator | Assigned technical/commercial evaluation | Sees only assigned events and permitted evaluation sections |
| Budget owner / approver | Approve or reject within delegated scope and limits | Cannot approve beyond limit or after approval becomes stale |
| Finance user | Budgets, invoice review, matching, payment-status reconciliation | No unreviewed supplier banking-detail changes |
| Receiver | Record deliveries, inspections, returns | Cannot change PO commercial terms |
| Legal / risk reviewer | Contract clauses, exceptions, evidence review | Cannot claim unverified risk signals are established facts |
| Supplier administrator / contributor | Maintain own profile, submit offers, acknowledge POs | Cannot access competitors, internal notes, or unrelated buyer data |
| Auditor | Read and export permitted historical evidence | No operational mutations |
| Platform operator | Infrastructure and support | No routine access to customer documents; audited, time-limited support access |

Implement RBAC plus resource-level checks for tenant, department, assignment, amount, and workflow state. The API enforces permissions independently of the UI. A user can belong to multiple organizations, but every request operates in one explicitly selected membership context.

Approval delegation has effective dates, scope, and amount limits; it cannot create a self-approval bypass. Removing a user revokes sessions and integration credentials as appropriate and reassigns pending work with an audit trail. Supplier relationships and visibility are scoped to the buyer organization even where supplier identity is shared.

## 3. End-to-end operating journey

1. Administrator configures organization, currency, cost centers, roles, budgets, approval rules, retention, and categories.
2. Requester drafts a requisition with line items, quantity, specifications, acceptable alternatives, deadline, delivery location, and business justification.
3. Required approvers authorize the request and budget reservation according to the configured policy.
4. Procurement publishes a versioned RFQ to invited suppliers with a deadline, evaluation criteria, terms, and required documents.
5. Suppliers ask questions and submit structured offers and attachments. Material shared clarifications reach all relevant bidders.
6. Uploaded files pass security checks; extraction produces proposed fields with source evidence and review status.
7. Reviewers resolve ambiguous terms and verify critical commercial fields before offers become eligible for award.
8. The system checks hard requirements, computes deterministic scores, and optionally optimizes allocation across suppliers.
9. Procurement prepares an evidence-backed recommendation. Authorized humans approve or reject the exact award version.
10. ProcureX issues approved POs, records supplier acknowledgements, and handles controlled amendments.
11. Receivers record partial/full delivery, accepted and rejected quantities, and returns.
12. Finance matches invoices to PO and accepted receipts, resolves exceptions, and exports authorized records to accounting.
13. Procurement closes the order after obligations and exceptions are resolved, with supplier performance and an exportable audit record.

Every stage must support assigned ownership, visible status, useful empty/error states, recovery actions, notifications, and permission-aware history.

## 4. Functional requirements and acceptance criteria

Requirement IDs are stable identifiers for tickets, tests, and release evidence. Unless labeled R3, these are required by R2; the phase plan identifies the R1 subset.

### 4.1 Organization and administration

| ID | Requirement | Acceptance evidence |
|---|---|---|
| ORG-01 | Organization onboarding, memberships, invitations, departments, cost centers, locations, and categories | A new organization completes onboarding without database intervention |
| ORG-02 | MFA for privileged users, secure recovery, session/device revocation, and invitation expiry | Expired/revoked access fails at the API; recovery actions are audited |
| ORG-03 | Versioned approval policies, thresholds, quorum, delegation, escalation, absence handling | Policy simulator shows required approvers for representative requests |
| ORG-04 | Locale, currency, business calendar, timezone, retention, notification, and AI configuration | Configuration changes have effective dates and preserve historical interpretation |
| ORG-05 | Tenant export, closure, legal hold, and deletion lifecycle | Deletion reaches active storage, indexes, caches and provider artifacts; backup expiry is documented |
| ORG-06 | Usage limits and operator administration | Per-tenant quotas prevent noisy-neighbor overload without dropping durable work |

### 4.2 Requisitions and budgets

| ID | Requirement | Acceptance evidence |
|---|---|---|
| REQ-01 | Draft/save/duplicate requests; line items, attachments, custom category fields | Quantity, units, date and money validation work in API and UI |
| REQ-02 | Structured mandatory/preferred requirements and AI-assisted requirement drafts | Draft suggestions require confirmation; every mandatory requirement has a testable criterion |
| REQ-03 | Approval, rejection, revision, cancellation, comments, and status tracking | Unauthorized and invalid transitions fail consistently |
| REQ-04 | Department/project budget allocations, reservations, commitments, releases, and variance | Concurrent approvals cannot consume the same available balance twice |
| REQ-05 | Emergency/sole-source exceptions | Authorized exception path records justification, scope, policy reference and approval |

Budget accounting must define available, reserved, committed, and consumed amounts without double counting. Converting an approved requisition reservation into a PO commitment is atomic; rejection, cancellation, and amendment apply corresponding ledger movements. The customer selects whether consumption occurs at receipt or invoice and this policy is versioned.

### 4.3 Supplier onboarding and master data

| ID | Requirement | Acceptance evidence |
|---|---|---|
| SUP-01 | Supplier profiles, contacts, categories, locations, capabilities, certificates and expiry | Suppliers can update their own permitted fields; buyer review is visible |
| SUP-02 | Invitation, verification, approval, suspension, duplicate review and controlled merge | Duplicate suggestions do not merge companies automatically |
| SUP-03 | Buyer-specific qualification and approved-supplier status | Suspended/unqualified suppliers cannot receive awards without authorized exception |
| SUP-04 | Performance records for delivery, quality, disputes, response time and fulfilled quantity | Metrics show period, sample size, exclusions, source events, and correction history |
| SUP-05 | Sensitive payment/contact changes | Bank details are minimized; changes require independent verification and dual review where collected |
| SUP-06 | Qualification reminders and supplier corrections/appeals | Expired documents create tasks; disputed adverse findings remain visibly contested |

### 4.4 RFQs and supplier portal

| ID | Requirement | Acceptance evidence |
|---|---|---|
| RFQ-01 | RFQ templates, lots/items, quantities, specification, delivery and commercial terms | Published RFQ is immutable; amendments create versions |
| RFQ-02 | Invitation lists, submission deadlines, timezone display and acknowledgements | Server receipt time determines timeliness; policy defines late-offer handling |
| RFQ-03 | Clarification threads, attachments and fair distribution of shared answers | Suppliers never see competitors' confidential messages |
| RFQ-04 | Structured quote forms, document upload, drafts, revisions, withdrawal, alternatives | Every submission has a receipt and immutable version; totals can be reconciled |
| RFQ-05 | Optional sealed commercial offers and controlled bid opening | Commercial data remains inaccessible to buyer roles and jobs until authorized opening |
| RFQ-06 | Deadline extensions, cancellation, no-bid and insufficient-bid workflows | Amendments notify affected suppliers and invalidate impacted downstream evaluations |
| RFQ-07 | Multi-round clarification and negotiation assistance | AI creates reviewable drafts; only authorized users send supplier communications |

Clarify whether tax, freight, duties, installation, warranty, training, recurring fees and discounts are included. Capture quote validity, price breaks, minimum order quantities, capacity, partial-award permission, payment terms and delivery assumptions. A quote saying “delivery after advance payment” must not silently become “delivery after PO.”

### 4.5 Document processing and evidence

| ID | Requirement | Acceptance evidence |
|---|---|---|
| DOC-01 | PDF/image/XLSX/DOCX intake with explicit size/page/type limits | Unsupported, malicious, password-protected and unreadable files receive actionable outcomes |
| DOC-02 | Quarantine, malware scanning, sandboxed parsing, OCR and table extraction | Files cannot be downloaded as trusted artifacts or parsed before required checks succeed |
| DOC-03 | Typed extraction of supplier, line items, amounts, currency, taxes, terms and specifications | Schema validation catches malformed or incomplete output |
| DOC-04 | Field-level provenance | Each extracted critical value links to document version and page/bounding box or sheet/cell |
| DOC-05 | Review workspace with original/normalized values, correction history and unresolved queue | Users can inspect the source and correct fields without overwriting original evidence |
| DOC-06 | Reprocessing and deduplication | Reprocessing creates an extraction version; reused files preserve submission-specific provenance |
| DOC-07 | Search, authorized downloads, retention and legal hold | Search/index/download permissions match source permissions |

Never infer absent values as zero or “compliant.” Distinguish **missing**, **illegible**, **ambiguous**, **conflicting**, **not applicable**, and **verified**. Extracted prices, quantities, currencies, tax treatment and delivery basis require human verification in R1. Later automation is allowed only for validated field classes with monitored error rates and an approved policy.

### 4.6 Compliance, comparison, and risk

| ID | Requirement | Acceptance evidence |
|---|---|---|
| EVAL-01 | Requirement checks with pass/fail/unknown/not-applicable states | Unknown mandatory requirements block eligibility until resolved or formally waived |
| EVAL-02 | Side-by-side comparison with landed cost and technical requirements | Comparison identifies currency conversion, exclusions, assumptions and missing terms |
| EVAL-03 | Versioned deterministic weighted scoring | Repeated evaluation of identical inputs produces identical scores |
| EVAL-04 | Explainable supplier risk signals | Every signal includes evidence, recency, confidence/limitations and review state |
| EVAL-05 | Evidence-grounded summaries and document Q&A | Unsupported answers abstain; citations resolve to authorized source versions |
| EVAL-06 | Evaluation assignments, independent reviews, disagreements and conflict declarations | Unresolved material disagreement and conflict-of-interest states are visible before award |
| EVAL-07 | Scenario comparison and sensitivity analysis | Users can see when changed weights, budget or delivery limits change the recommendation |

Keep price, capability, observed performance and external risk separate. Lack of delivery history is “insufficient data,” not low risk or poor performance. External adverse reports require licensed/permitted sources, entity matching, timestamps, review and correction paths. Do not invent a universal risk probability from arbitrary weighted signals.

### 4.7 Award and purchase orders

| ID | Requirement | Acceptance evidence |
|---|---|---|
| AWD-01 | Single/split awards and allocation proposals | Award quantities satisfy approved demand and quote capacity constraints |
| AWD-02 | Recommendation dossier, approvals, rejection and resubmission | Approval binds to an immutable evaluation/award snapshot |
| AWD-03 | Reapproval following material change | Price, allocation, supplier, requirement or policy-sensitive changes invalidate affected approvals |
| AWD-04 | Human override with reason and approved exception limits | Overrides cannot silently bypass non-waivable controls |
| PO-01 | PO generation, organization numbering, PDFs and issuance | One approved issue request produces one PO despite retries |
| PO-02 | Supplier acknowledgement, rejection, proposed changes and attachments | Supplier acceptance never silently changes approved PO terms |
| PO-03 | Controlled amendments, cancellations and closure | Amendments adjust commitments atomically and preserve prior documents |
| PO-04 | Buyer-selected supplier notifications and award outcomes | No confidential competitor evaluation is disclosed to losing bidders |

### 4.8 Delivery, invoices, contracts and monitoring

| ID | Requirement | Acceptance evidence |
|---|---|---|
| OPS-01 | Partial receipts, inspections, accepted/rejected quantities and delivery evidence | Cumulative receipts and tolerances reconcile to PO lines |
| OPS-02 | Returns, replacements, shortages, damage and warranty/service claims | Return links to receipt; credit/replacement and quantities are tracked independently |
| OPS-03 | Invoice capture, duplicate detection and credit notes | Duplicate vendor invoice numbers and suspicious content matches enter review |
| OPS-04 | PO/receipt/invoice three-way matching with configured tolerances | Price, quantity, currency and tax mismatches create blocked exceptions |
| OPS-05 | Non-PO invoice policy and disputes | Unsupported invoices are explicitly rejected or routed through a separate authorized exception path |
| OPS-06 | Accounting export, payment-status import and reconciliation | Retried exports do not create duplicates; mismatches have an owned resolution queue |
| OPS-07 | Contract repository, linked awards/POs, obligations, renewals and reminders | Extracted obligations are confirmed by a reviewer before activation |
| OPS-08 | Supplier monitoring and procurement closure | Closure checks unresolved deliveries, invoices, claims and obligations |

R2 contracts support uploaded executed agreements and confirmed obligations. Clause libraries, redlining, electronic-signature integration, catalogs/punchout, blanket POs, milestone-based services and subscription purchasing belong to R3 and need separate workflow specifications.

### 4.9 Reporting, collaboration and administration

- **REP-01:** Dashboards for spend, open commitments, cycle time, sourcing funnel, savings, supplier concentration, late delivery and exception backlog.
- **REP-02:** Savings distinguish negotiated price difference from realized savings; report the baseline, period and calculation.
- **REP-03:** Permission-aware CSV/XLSX/PDF exports and scheduled reports with protected download links and export audit events.
- **REP-04:** Comments, mentions, task inbox, email/in-app notifications, preferences and escalations. Delivery failures are observable and retryable.
- **REP-05:** Historical evidence package containing originals, RFQ versions, corrections, scoring rules, decisions, approvals and event history.
- **REP-06:** Support console, tenant usage, incidents, job retry controls and configuration history with least-privilege access.

## 5. User experience and screen inventory

| Area | Required screens |
|---|---|
| Access | Sign in, MFA, invitation acceptance, recovery, organization selection |
| Setup | Organization wizard, users/roles, cost centers, policies, budgets, integrations |
| Buyer home | Work queue, dashboards, notifications, assigned approvals |
| Requisitions | List/filter, create/edit, detail, budget impact, approval history |
| Suppliers | Directory, qualification review, profile, performance, document expiry |
| Sourcing | RFQ builder, invitations, clarifications, submission tracker, bid opening |
| Supplier portal | Buyer invitations, RFQs, quote editor, uploads, receipt, PO acknowledgement |
| Intelligence | Processing status, extraction review, evidence viewer, requirement matrix |
| Decisions | Comparison, score breakdown, risk review, allocation scenarios, award approval |
| Operations | PO detail/amendments, receipt, return, invoice match, dispute and contract tasks |
| Governance | Audit search/export, retention, integration failures, support and usage |

All screens require loading, empty, unauthorized, expired-session, validation, conflict, failure, and retry states. Show progress for asynchronous work and preserve user drafts. Use keyboard-accessible controls, visible focus, labeled inputs, usable table navigation and statuses that do not depend on color alone. Aim for WCAG 2.2 AA and verify with automated and manual accessibility testing; the criteria are defined by [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/).

Money always displays currency. Date/time fields show timezone. Destructive business actions show the affected object and consequence. Critical actions return a durable receipt/status, so a network timeout does not encourage accidental repetition.

## 6. Architecture and technology decisions

### 6.1 Initial architecture

Use a **modular monolith with independently scaled workers**. Domain boundaries matter from day one; separate microservices are justified later by independent scaling, release ownership or isolation needs.

```text
Buyer web / Supplier portal
            |
     HTTPS edge + API
            |
  Identity and tenant authorization
            |
 Procurement | Suppliers | Documents | Evaluation | Orders | Finance
            |                  |
    PostgreSQL + outbox     Cloudinary authenticated assets
            |
       Durable job broker
            |
 OCR/parser workers | Evaluation workers | Integration workers
            |
 Provider adapters: LLM, OCR, email, ERP, exchange rates

Cross-cutting: policy enforcement, audit, secrets, telemetry, backups
```

### 6.2 Proposed baseline stack

These are design choices to validate in Phase 0, not claims that one stack is universally best. Pin supported versions after compatibility and security review; record the choices in architecture decision records (ADRs).

| Layer | Proposed choice | Purpose / constraint |
|---|---|---|
| Web | Next.js + TypeScript | Buyer and supplier interfaces; generated API types |
| API | Python FastAPI + Pydantic | Typed contracts and proximity to document/optimization workloads |
| Persistence | PostgreSQL + SQLAlchemy + Alembic | Transactional business state, migrations and audit references |
| Retrieval | PostgreSQL full-text search; pgvector if benchmarked useful | Tenant-filtered hybrid evidence search |
| File storage | Cloudinary | Authenticated image/raw assets, immutable original IDs and short-lived server-signed downloads |
| Background jobs | Celery + RabbitMQ | Durable task dispatch; application-level idempotency and recovery |
| Cache/rate limits | Redis if needed | Ephemeral data; never authoritative approval/budget state |
| AI application layer | LangChain Python | Provider adapters, prompts, tools, retrieval, embeddings and Pydantic-validated structured output |
| AI orchestration | LangGraph Python | Explicit state graphs, durable checkpoints, bounded retries, branching and human review interrupts |
| Optimization | OR-Tools CP-SAT | Integer allocation and hard constraints |
| Identity | Established OIDC provider | Authentication, MFA and lifecycle support |
| Telemetry | OpenTelemetry plus managed metrics/logs/error tracking | Correlated requests, jobs, model calls and business failures |
| Delivery | Containers, CI/CD and infrastructure as code | Reproducible staging and production |

Start with managed compute, database and Cloudinary. Kubernetes, Kafka, graph databases and independent domain services are optional future ADRs, not prerequisites. Do not operate infrastructure solely to make the architecture look larger.

### 6.3 Cloudinary asset policy

Cloudinary is the selected managed file service for R1 and R2. All procurement documents are uploaded server-side with signed requests as `authenticated` assets; use the `raw` resource type when exact document bytes must be preserved and no media transformation is required. The default public `upload` delivery type is prohibited for customer documents. New assets remain quarantined in ProcureX and unavailable to users or AI workers until the separate malware and file-validation pipeline succeeds. Browser uploads, if later enabled, require a narrowly scoped signed upload generated by the API and the same authorization, type, size and format policy as server uploads.

PostgreSQL remains authoritative for ownership and lifecycle metadata. Each `DocumentVersion` stores the Cloudinary `asset_id`, `public_id`, `resource_type`, delivery type, provider version, byte count, MIME type, original content hash and upload response signature. Provider folders, tags or public IDs are organizational aids, not tenant authorization boundaries. Downloads and previews require application authorization followed by a short-lived signed Cloudinary URL; never persist delivery URLs as access grants.

Use a create-only identifier for every immutable document version and disable overwrite. A corrected or replaced file creates a new ProcureX document version and a new Cloudinary asset. Enable Cloudinary automatic backup only after its retention, residency, restore, cost and deletion behavior pass Phase 0 review. Tenant deletion and legal-hold procedures must cover originals, eager derivatives, CDN invalidation and backed-up versions. A periodic reconciler detects database records without provider assets and unreferenced provider assets without deleting either automatically.

### 6.4 Suggested repository layout

```text
apps/web/
services/api/app/{identity,procurement,suppliers,documents,evaluation,orders,finance}/
services/workers/{documents,ai,integrations}/
services/workers/ai/{graphs,nodes,schemas,prompts,tools,retrieval}/
packages/api-client/
contracts/{openapi,events}/
db/migrations/
infra/{environments,modules}/
tests/{unit,integration,e2e,security,performance,fixtures}/
evals/{datasets,rubrics,runs}/
docs/{adr,product,threat-model,runbooks,release-evidence}/
```

Domain modules own writes to their tables. Cross-domain changes go through application services in explicit transactions. Keep business rules out of web components and LLM prompts.

## 7. Data model and invariants

### 7.1 Core entities

| Domain | Entities |
|---|---|
| Identity | Organization, User, Membership, Role, Permission, Delegation, AccessGrant |
| Procurement | Requisition, RequisitionVersion, RequisitionLine, Requirement, CostCenter, Budget, BudgetEntry |
| Sourcing | RFQ, RFQVersion, RFQLine, Invitation, Clarification, Submission, QuoteVersion, QuoteLine |
| Supplier | SupplierIdentity, BuyerSupplierRelationship, Contact, Qualification, Certificate, PerformanceObservation |
| Documents | Document, DocumentVersion, CloudinaryAsset, ScanResult, Page, ExtractedField, EvidenceAnchor, ReviewCorrection |
| Intelligence | AnalysisRun, ModelInvocation, RequirementCheck, RiskSignal, ScoringPolicy, EvaluationSnapshot |
| Optimization | Scenario, ConstraintSet, OptimizationRun, Allocation, SolverResult |
| Governance | ApprovalPolicyVersion, ApprovalRequest, ApprovalDecision, Exception, AuditEvent |
| Operations | Award, AwardLine, PurchaseOrder, POLine, Amendment, Receipt, ReceiptLine, Return, Claim |
| Finance | Invoice, InvoiceLine, CreditNote, MatchResult, Dispute, AccountingExport, PaymentStatus |
| Contracts | ContractVersion, Obligation, Renewal, Reminder |
| Platform | OutboxEvent, InboxReceipt, Job, Notification, IntegrationConnection, SyncCursor, UsageRecord, LegalHold |

Every tenant-owned record carries `organization_id`; composite keys/constraints prevent cross-tenant references. A supplier submission includes the buyer organization and authorized supplier relationship. Store human and service actors explicitly.

### 7.2 Non-negotiable invariants

- Use exact decimal arithmetic for prices/taxes and currency-aware rounding. Never use binary floating point for authoritative money.
- Store quantity with unit and allowed precision. Convert only through explicit, validated unit mappings.
- Preserve original currency and separately store normalized comparison values, rate source, timestamp and rounding policy.
- Store timestamps in UTC and preserve relevant business timezone and original date assumptions.
- Published RFQs, submitted quote versions, approved awards and issued POs are immutable business versions.
- Content hashes identify document bytes; corrections and new attachments never erase originals.
- Evidence anchors reference immutable source versions and extraction coordinates.
- Approvals bind to a snapshot/version digest and policy version, not merely a mutable object ID.
- Database constraints enforce uniqueness for submission versions, PO numbers, external mappings and scoped idempotency keys.
- Optimistic concurrency protects editing; transactional locks protect budget consumption, award issuance and other competing mutations.
- Tenant-scoped delete/archive rules preserve required audit references and respect legal holds.
- Reporting projections are rebuildable from authoritative records and disclose refresh time.

PostgreSQL row-level security is a defense layer alongside application authorization. Runtime roles must not be superusers, table owners with bypass behavior, or have `BYPASSRLS`; review `FORCE ROW LEVEL SECURITY` where appropriate and test connection-pool tenant context reset. See [PostgreSQL row security documentation](https://www.postgresql.org/docs/17/ddl-rowsecurity.html).

## 8. Workflow state machines and failure behavior

| Object | Main states | Important exceptional paths |
|---|---|---|
| Requisition | Draft → Submitted → Approved → Sourcing → Ordered → Closed | Changes requested, rejected, cancelled |
| RFQ | Draft → Published → Closed → Evaluating → Awarded | Amended, extended, cancelled, no valid offers |
| Submission | Draft → Submitted → Under review → Verified | Superseded, withdrawn, late, disqualified |
| Document | Quarantined → Scanning → Parsing → Extracted → Reviewed | Rejected, failed, needs manual entry |
| Analysis | Queued → Running → Awaiting review → Completed | Retry scheduled, failed, cancelled, stale |
| Award | Draft → Pending approval → Approved → Issued | Rejected, invalidated, cancelled |
| PO | Draft → Approved → Issued → Acknowledged → Partially received → Received → Closed | Change requested, amended, cancelled, disputed |
| Invoice | Captured → Validated → Matched → Approved for export → Exported → Settled | Duplicate suspected, mismatch, disputed, credited, voided |

Each transition specifies allowed actors, preconditions, atomic mutations, version checks, audit event and notifications. The state-machine specification must define all permitted exceptional transitions, not just the happy path shown here. Order delivery, financial and dispute statuses may be separate dimensions to represent “fully received but disputed” accurately.

Mandatory failure scenarios:

- Submission and bid-close race: enforce a single server deadline and atomic receipt rule.
- Worker crashes after side effect but before acknowledgement: recover using business idempotency keys.
- Approval arrives after quotation/RFQ change: reject as stale and create a new approval request.
- Provider timeout or malformed AI output: bounded retry, then manual workflow; never fabricate completion.
- OCR unavailable: keep originals and allow reviewed manual entry.
- Supplier withdraws/expires after recommendation: invalidate affected allocations and seek reapproval.
- PO delivery email fails: retain issued state, expose delivery failure and resend the same version.
- Accounting accepts an export but response is lost: query by stable external reference before retrying creation.
- Tenant membership revoked during a job: recheck authorization before sensitive side effects/download delivery.

## 9. API, events and integration contracts

### 9.1 API conventions

Use versioned `/api/v1` endpoints and OpenAPI-generated clients. Define pagination, supported filters, stable sort order, request IDs, structured errors, field-level validation and documented rate limits. Tenant context comes from authenticated membership, not an untrusted body field.

Example resource groups:

```text
/organizations /memberships /policies /budgets
/requisitions /suppliers /rfqs /submissions
/documents /extractions /reviews
/evaluations /scenarios /optimization-runs /awards
/approvals /purchase-orders /receipts /returns
/invoices /disputes /contracts /reports
/audit-events /integrations /jobs
```

Use explicit commands such as `POST /awards/{id}/submit` and `POST /purchase-orders/{id}/issue`. Enforce idempotency on consequential creates/commands; reuse with a different payload must fail. Use expected versions or ETags for updates. Long work returns `202` and a job resource with progress, errors and authorized retry/cancel operations. State transitions return conflicts rather than silently overwriting competing changes.

### 9.2 Durable events

Persist business state and an outbox entry in the same database transaction. Publish with retry. Consumers maintain an inbox/deduplication record and apply idempotent effects. Assume **at-least-once delivery**, not global exactly-once execution.

Event envelope: `event_id`, `schema_version`, `organization_id`, `aggregate_id`, `aggregate_version`, `event_type`, `occurred_at`, `actor_id`, `correlation_id`, `causation_id`, and a minimal payload/reference.

Events include `requisition.approved`, `rfq.published`, `quote.submitted`, `document.reviewed`, `evaluation.completed`, `award.approved`, `po.issued`, `receipt.accepted`, `invoice.matched`, and `integration.failed`. Handle out-of-order versions and dead-letter queues. A scheduled sweeper detects stranded outbox entries and jobs; operator replay must not duplicate external actions.

### 9.3 Integrations

| Integration | R1 | R2 / later |
|---|---|---|
| Email | Invitations and notifications with delivery status | Bounce/complaint handling, templates and configured authenticated domain |
| Accounting / ERP | Structured export and sandbox adapter | One customer-selected production connector, mappings, reconciliation and support runbook |
| Currency | Reviewed manual rate snapshots | Approved feed with freshness policy and outage fallback |
| Identity | OIDC, MFA, lifecycle basics | Enterprise SSO and SCIM in R3 |
| Storage / OCR / AI | Provider abstraction and usage accounting | Data residency options and tested provider outage handling |
| External supplier signals | First-party performance | Licensed sources after coverage and quality validation |
| E-signature / catalogs | Outside R1 | R3 with provider-specific contracts and acceptance tests |

Every connector needs secret rotation, least-privilege scopes, rate-limit handling, stable external IDs, mapping ownership, schema change detection, retries, reconciliation, sandbox tests and a disconnect procedure. Webhooks require signature verification, replay protection, deduplication and constrained outbound destinations.

## 10. AI and evidence engineering

### 10.1 LangChain and LangGraph implementation decision

LangChain and LangGraph are required components of the ProcureX AI application layer. Use their Python packages behind ProcureX-owned interfaces so the business domain does not depend directly on framework message objects or provider-specific response formats.

Use **LangChain** for:

- chat-model and embedding provider adapters;
- prompt templates and versioned prompt metadata;
- Pydantic-backed structured output for extraction, requirement findings, citations and summaries;
- tenant-filtered retrievers over authorized document chunks; and
- a small allowlist of read-only tools with typed inputs and outputs.

Use **LangGraph** for workflows that need branching, checkpointed recovery, or human review. The first two production graphs are:

1. `document_analysis_graph`: load authorized document version → parse/OCR result → extract typed fields → validate evidence anchors and arithmetic → interrupt for critical-field review → finalize an extraction version.
2. `evaluation_graph`: load the immutable evaluation snapshot → retrieve authorized evidence → evaluate requirements → validate citations → draft a grounded comparison summary → interrupt for unresolved findings → finalize an analysis run.

Graph state is a versioned, minimal Pydantic/typed schema containing IDs and derived results, not entire documents, credentials or authoritative business objects. Every run has `organization_id`, `analysis_run_id`, `graph_name`, `graph_version`, `thread_id`, source-version digests and correlation identifiers. A production PostgreSQL-backed checkpointer must preserve resumable state; in-memory checkpointing is permitted only in unit tests and local prototypes. Checkpoint records inherit tenant isolation, retention, encryption and deletion rules.

Celery remains the durable queue and capacity-control boundary: it starts or resumes a graph run and handles scheduled/provider work. LangGraph controls the steps inside an AI run. PostgreSQL domain tables remain authoritative for documents, reviews, evaluations and approvals; graph checkpoints are execution state and cannot substitute for the audit log or business transactions.

Nodes must be small, typed and independently testable. Provider calls, retrieval and parsing are isolated behind injected interfaces. A node may write domain state only through an idempotent application command with a stable business key. Because a failed or interrupted node can replay, no node may directly issue a PO, send an award, approve a requisition or perform an unguarded external side effect.

Record the supported LangChain/LangGraph versions and upgrade policy in an ADR and lock file. Framework or model upgrades require graph contract tests and the frozen AI evaluation suite before rollout. LangSmith may be evaluated for development tracing, but production observability must work through OpenTelemetry and must not send customer prompts or documents to a third party without explicit approval and data-handling review.

### 10.2 Bounded pipeline

1. Intake and scan the immutable original.
2. Parse text/tables; OCR only when necessary; retain layout coordinates.
3. Extract proposed typed fields and evidence anchors.
4. Apply deterministic validation and commercial arithmetic checks.
5. Route missing/conflicting/critical fields to human review.
6. Evaluate confirmed mandatory requirements using deterministic rules where possible.
7. Retrieve only authorized, relevant evidence for semantic questions.
8. Draft summaries and tradeoffs from verified fields and cited passages.
9. Validate citation existence, relevance and access; mark unsupported findings unresolved.
10. Persist output, provenance, model/prompt/parser versions, cost, timing and review decisions.

Requirement, compliance and risk “agents” should be bounded nodes with typed inputs and outputs. They do not share unrestricted tools or recursively delegate. Stateful execution can use durable checkpoints and human interrupts; interrupted nodes may replay, so their side effects must be idempotent. See [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts).

### 10.3 Controls

- Treat supplier documents as untrusted data; embedded instructions cannot override system rules or trigger tools.
- No model has purchasing authority, approval authority, database-wide access or arbitrary outbound network access.
- Keep deterministic price arithmetic, taxes, eligibility and scoring outside the LLM.
- Do not expose hidden reasoning. Store structured findings, supporting evidence and concise explanations.
- Define provider retention/training settings, processing region, contractual permissions and redaction before sending real documents.
- Cap tokens, elapsed time, retries, tool calls and cost per run and per tenant.
- Model self-reported confidence is not an accuracy guarantee. Calibrate review policies on labeled held-out examples.
- Track unsupported claims, correction rates, extraction failures and drift by category and document type.
- Model/prompt upgrades require frozen evaluation runs, approval, gradual rollout and rollback capability.
- Manual processing remains available when AI is disabled or unavailable.
- Cache only within valid security boundaries and include source, prompt, model and policy versions in cache identity.

### 10.4 LangGraph acceptance criteria

- A killed worker can resume the same graph thread from a persisted checkpoint without duplicating finalized extraction, review tasks or analysis records.
- An interrupt exposes only the authorized review payload; resumption verifies tenant, actor permission, expected source versions and graph version.
- Changed or deleted source access makes a pending run stale or unauthorized rather than allowing it to continue on cached access.
- Every terminal run reports completed, failed, cancelled or stale status and correlates node/model activity with the durable application job and audit record.
- Tests cover normal routing, missing evidence, malformed structured output, bounded retry exhaustion, interrupt/resume, replayed nodes, cancellation and provider outage.
- Graph recursion, node attempts, model/tool calls, tokens, elapsed time and tenant cost are capped and observable.
- No graph output becomes an award, approval, PO or payment action without the deterministic checks and human authorization defined elsewhere in this roadmap.

## 11. Deterministic scoring and constrained allocation

### 11.1 Eligibility precedes ranking

Filter by confirmed hard requirements, quote validity, supplier qualification and permitted exceptions before ranking. A cheap ineligible offer cannot outrank an eligible one. Publish scoring policy before evaluation and version any authorized change.

For eligible offer `i`, define normalized criterion values `s_ik` using documented fixed anchors and weights `w_k`:

```text
score_i = sum_k(w_k * s_ik)
0 <= s_ik <= 100; w_k >= 0; sum_k(w_k) = 1
```

Specify ties, rounding, missing-value handling and direction of preference. Fixed anchors reduce ranking changes caused solely by adding an irrelevant bidder. Show each contribution and raw value. Weight changes produce a new evaluation; sensitivity views make subjective tradeoffs visible.

### 11.2 Allocation model

For supplier `i` and item `j`:

- `x_ij`: integer units awarded, nonnegative; fractional units require explicit integer scaling.
- `y_i`: binary indicator that supplier `i` receives any award.
- `d_j`: required units.
- `u_ij`: verified offered capacity.
- `c_ij`: normalized landed unit cost in scaled integer currency units.
- `f_i`: fixed supplier/order charge.
- `e_ij`: 1 only if the offer satisfies all non-waived hard constraints, otherwise 0.
- `m_ij`: minimum quantity when that offer is selected; model with item-level binary `z_ij`.

Baseline objective and constraints:

```text
minimize sum_i,j(c_ij * x_ij) + sum_i(f_i * y_i)

sum_i(x_ij) = d_j                         for each item j
0 <= x_ij <= u_ij * z_ij                  for each offer i,j
m_ij * z_ij <= x_ij                       for each offer i,j
z_ij <= e_ij; z_ij <= y_i                 for each offer i,j
y_i <= sum_j(z_ij)                        for each supplier i
sum_i,j(c_ij*x_ij) + sum_i(f_i*y_i) <= B   approved budget B
sum_i(y_i) <= K                          if a supplier-count limit applies
```

Delivery, quality and reviewed risk thresholds determine eligibility or have explicitly modeled constraints. If split awards are forbidden, enforce one selected supplier per applicable lot and its complete quantities. Set a positive minimum selected quantity so a selected offer cannot contain zero allocation.

Tiered prices, tax thresholds, minimum order values, freight breaks and discounts need explicit piecewise constraints and reconciliation against the final award totals; the baseline linear unit-cost model does not cover them automatically. Allow surplus only through a configured, approved tolerance with an explicit objective treatment.

Return solver status, runtime, objective, bound/gap when available, allocations and constraint checks. A feasible timeout result must not be labeled optimal. Infeasibility returns actionable conflicting constraints; propose relaxation scenarios separately and require approval before changing hard constraints. Independently validate the solver output before it can become an award. OR-Tools documents integer modeling and solver outcomes in its [CP-SAT guide](https://developers.google.com/optimization/cp/cp_solver).

## 12. Security, privacy and governance

Use OWASP ASVS as a traceable verification baseline, targeting applicable Level 2 controls with documented exceptions and review evidence. This is a testing target, not a certification claim. See the [OWASP ASVS project](https://owasp.org/projects/asvs).

Required controls:

- Threat model for tenant escape, supplier impersonation, document exploits, prompt injection, quote leakage, approval bypass, invoice fraud and privileged support misuse.
- TLS, encryption at rest, managed secrets, rotation, environment separation and restricted service identities.
- Secure cookies/session handling, CSRF protection where relevant, strict CORS, output encoding, upload restrictions, SSRF protections and dependency scanning.
- Cloudinary customer assets use authenticated delivery; the API issues short-lived signed URLs only after authorization. Derived previews are eagerly generated or otherwise protected, use safe content disposition, and render in isolation.
- Malware scanning and parsers with network isolation, resource limits, timeouts and safe archive handling.
- Tenant filtering for tables, files, vector retrieval, caches, background jobs, exports and telemetry.
- Sensitive fields masked in logs; provider payload logging disabled or explicitly redacted.
- Tamper-evident audit with restricted writers, append-only application behavior and independently retained audit exports. A hash chain alone does not defeat an administrator who can rewrite both data and hashes.
- Audit record includes actor, organization, action, object/version, timestamp, request ID, reason and safe before/after references.
- Retention schedules by record class, legal holds, deletion verification and documented backup aging.
- Security incident, credential compromise, leaked quotation and supplier account takeover runbooks.
- Independent security review before R2, including cross-tenant tests and authentication/authorization abuse cases.

Legal/tax requirements must be maintained as versioned jurisdiction configurations reviewed by appropriate specialists. Do not describe the application as compliant with a law or certification merely because its controls appear in this roadmap.

## 13. Reliability, performance and operating targets

Targets below are proposed acceptance thresholds; benchmark and approve them during discovery. Report both exclusions and measured results.

| Area | Initial target and measurement |
|---|---|
| Availability | 99.5% monthly for R1 pilot; 99.9% for R2 core API/web, measured by external probes |
| Interactive latency | p95 under 500 ms for ordinary API reads and under 1 s for writes, excluding async/provider work |
| Document pipeline | p95 under 3 minutes for a defined 20-page supported document fixture at target load; scanned and native PDFs reported separately |
| Comparison | p95 under 2 s for deterministic comparison of 50 offers × 100 lines on benchmark hardware |
| Optimization | 30 s default time budget; return honest solver status and a feasible candidate only if validated |
| Pilot scale | 20 tenants, 100 concurrent users, 50,000 stored documents; benchmark with realistic skew and queue bursts |
| Recovery | R2 RPO ≤15 minutes and RTO ≤4 hours, verified by restoration exercise |
| Integrity | No accepted duplicate PO issuance, unauthorized approval or cross-tenant disclosure in release tests |
| Usability | At least 80% of representative pilot users complete the core task without facilitator intervention |

Monitor API error/latency, DB saturation, queue age, document failure rates, stuck approvals, notification delivery, provider spend, solver failures, outbox delay and connector reconciliation gaps. Alerts need owners and runbooks; page on user impact, not every transient retry.

Use bounded queues, per-tenant quotas, worker concurrency limits, backpressure and provider circuit breakers. Reserve capacity for interactive actions so a large OCR batch cannot block approvals. Budget the whole service: hosting, database, Cloudinary storage/backup/transformation/bandwidth, OCR, AI, email, monitoring and support. Measure cost per RFQ and per processed document before setting commercial prices.

## 14. Testing and research evaluation

### 14.1 Software verification

| Layer | Required coverage |
|---|---|
| Unit/property tests | Money, units, scoring, eligibility, allocation invariants, budget ledger and transitions |
| Integration tests | Real PostgreSQL isolation/RLS, transactions, object permissions, broker replay, migration behavior |
| API contract tests | Schemas, permissions, concurrency conflicts, idempotency and version compatibility |
| End-to-end tests | Buyer/supplier workflows, approval changes, PO, receipt, matching and correction paths |
| Security tests | IDOR, tenant leakage, privilege escalation, hostile uploads, prompt injection and signed URL exposure |
| Resilience tests | Worker death, provider outage, duplicate/out-of-order events, broker/DB restart and interrupted export |
| Performance tests | Interactive concurrency, large quotes, document bursts, slow tenants and optimizer limits |
| Accessibility tests | Automated checks plus keyboard and screen-reader review of essential workflows |
| Operational tests | Backup restore, key rotation, rollback, tenant export/deletion and alert delivery |

Critical release scenarios include two approvers competing for the same budget; an altered quote after approval; a supplier attempting to read a competing offer; a repeated PO issue request; a late submission at the deadline; two partial receipts against one invoice; a return followed by a credit; a provider outage during analysis; and an accounting timeout after successful creation.

### 14.2 AI dataset and experiment design

Prepare a permissioned, labeled starting set of approximately 200–500 documents across 30–50 RFQ scenarios, with scanned/native PDFs, spreadsheets, layout variation, currencies, conflicting terms and incomplete offers. These are collection targets; confirm achievable diversity in Phase 0. Split by supplier/template/RFQ family to reduce leakage. Preserve a frozen held-out set; never tune on test results.

Annotate required fields, units, line associations, source anchors, eligibility decisions and known ambiguities. Two reviewers label a representative subset, measure agreement and resolve differences with a documented rubric. Report synthetic and real-document results separately.

Research question: **Does evidence-grounded structured procurement analysis improve evaluation accuracy, consistency and traceability compared with manual and LLM-only evaluation?**

Compare:

1. Manual evaluation with a fixed rubric.
2. LLM-only evaluation of the same supplied documents.
3. Structured extraction plus deterministic checks and a single grounded analysis pipeline.
4. Optional bounded multi-agent pipeline using identical evidence and comparable resource budgets.

Measure field accuracy, critical-field error, requirement classification, unsupported-claim rate, citation correctness, reviewer correction time, total task time, repeated-run agreement, cost and allocation feasibility. Use matched cases, counterbalanced task order, consistent human assistance and uncertainty intervals. Run ablations for retrieval, validation and multi-agent coordination. Multi-agent orchestration is a hypothesis to test, not a guaranteed contribution.

Provisional gates on the frozen set:

- ≥95% exact normalized accuracy for critical extracted fields; show per-field and scan-quality results.
- ≥98% correct supporting citations among sampled factual claims; source existence alone is insufficient.
- Zero observed unsupported claims designated critical in the release evaluation; document sample size and uncertainty.
- All uncertain critical fields still require review regardless of aggregate accuracy.
- 100% independent feasibility validation for accepted optimizer outputs.
- Any time-saving claim includes workload, participant count, baseline and confidence interval.

If gates fail, reduce supported formats/categories, improve extraction/review or keep the feature assistive. Do not weaken purchasing controls to improve demo completion rates.

## 15. Delivery plan: 32-week FYP and controlled-pilot candidate

Each phase must produce working vertical slices, tests and documentation. Demonstrate integrated behavior at the end of every two-week iteration. Time estimates are planning assumptions, not commitments.

| Phase | Weeks | Main deliverables | Dependencies / exit gate |
|---|---|---|---|
| P0: discovery | 1–2 | User interviews, workflow maps, category schema, scope, threat model, data permissions, stack/provider ADRs, acceptance backlog | Obtain feedback from requesters, procurement, finance and suppliers; choose pilot category and success metrics |
| P1: foundation | 3–5 | Repository, CI, dev/staging, identity, organizations, permission model, DB migrations, Cloudinary adapter and authenticated asset policy, queue, audit, telemetry; LangChain/LangGraph ADR, pinned dependencies, graph state/checkpoint schema and tracing scaffold | Tenant isolation tests pass across API/Cloudinary assets/jobs/checkpoints; signed delivery and deletion/reconciliation tests pass; a sample graph survives worker restart in staging; reproducible setup and staging deployment |
| P2: requisition and supplier | 6–8 | Request forms, budgets, approvals, supplier onboarding and directory | Approved requisition reserves budget safely; supplier role boundaries pass |
| P3: sourcing | 9–11 | RFQ publishing, invitations, portal submissions, revisions, clarifications and deadlines | Two suppliers submit against a versioned RFQ; deadline/revision tests pass |
| P4: documents | 12–15 | Secure upload, parsing/OCR, LangChain structured extraction, `document_analysis_graph`, evidence viewer, interrupt/resume review and correction | Critical fields can be verified from originals; hostile and failed inputs have safe outcomes; graph replay does not duplicate results |
| P5: evaluation | 16–18 | Requirement matrix, landed cost, deterministic scores, first-party performance, authorized retrieval and `evaluation_graph` grounded summary | Same verified inputs reproduce scores; unknown requirements block eligibility; citations and graph recovery gates pass |
| P6: allocation and award | 19–21 | Solver, constraints, sensitivity, recommendation dossier and snapshot approvals | Infeasible/timeout cases handled; changed inputs invalidate approvals |
| P7: order operations | 22–24 | PO issue/acknowledgement, partial receipt, basic invoice matching and accounting sandbox/export | Full happy path plus duplicate/retry and mismatch scenarios pass |
| P8: stabilization | 25–28 | Security fixes, failure drills, performance tuning, accessible critical screens, backup restore and pilot onboarding | All R1 release checks pass; known limitations explicitly approved for supervised pilot |
| P9: evaluation and handover | 29–32 | Controlled user study, frozen benchmark, thesis/report, demo, user guides, runbooks and evidence archive | Reproducible results, accepted R1 scope and prioritized R2 backlog |

Current implementation progress: P2 now includes requisition drafts/submission, versioned approval
policies, quorum decisions, append-only budget reservations, and the first SUP-01 through SUP-03
buyer-scoped supplier directory and qualification workflow. Supplier invitations/self-service,
duplicate-review/merge tooling, expiry automation, and sourcing eligibility enforcement remain in
the P2/P3 backlog and are not claimed complete.

P3 now has its first backend vertical slice: approved-requisition RFQ creation, approved-supplier
selection, immutable publication/amendment snapshots, revision-bound immutable quote versions,
deadline enforcement, and shared/private clarification records. Supplier portal identity and
object filtering, acknowledgements/no-bid, attachments, notifications, idempotency keys, and
end-to-end PostgreSQL isolation tests remain before the P3 exit gate is complete.

### 15.1 Suggested responsibilities

- Contributor A: buyer UI, design system and accessibility.
- Contributor B: transactional API, permissions, budgets, approvals and migrations.
- Contributor C: document pipeline, evidence, grounded analysis and research dataset.
- Contributor D: supplier portal, optimization, integrations and deployment automation.

Assign a second reviewer to every critical subsystem. Redistribute work after measured velocity; no person should be the only operator or reviewer of a production-critical component. Product validation, security and testing are shared responsibilities.

### 15.2 Critical path and safe scope reductions

Critical path: identity/isolation → requisitions/approvals → RFQ/submission versions → verified extraction → comparison → award snapshot → PO → receipt/match → recovery/security validation.

If behind schedule, defer external risk feeds, elaborate dashboards, multi-agent orchestration, additional file formats and additional categories. Preserve human review, access control, audit, deterministic arithmetic, idempotency and recovery. A narrower correct workflow is an acceptable FYP outcome; label the release scope honestly.

## 16. R2 production completion plan

Reserve a separate planning envelope of approximately 12–20 weeks after R1 for the assumed team; re-estimate from pilot defects and unfinished requirements. Do not treat this estimate as evidence that all enterprise features fit within it.

| Workstream | Completion requirements |
|---|---|
| Operational completeness | Returns/replacements, disputes, credit notes, full amendment/cancellation rules, closure and warranty claims |
| Financial controls | Tolerance policies, verified tax configuration, non-PO exceptions, production accounting connector and reconciliation |
| Contract basics | Executed contract repository, confirmed obligations, renewal/reminder ownership |
| Platform operations | Tenant lifecycle, quotas, support access, usage, incident handling, backup/restore and retention execution |
| Product polish | Complete help, onboarding, imports, exports, notification preferences and accessibility remediation |
| Assurance | Independent security review, realistic load tests, pilot fixes, dependency/provider review and documented residual risk |
| Customer launch | Customer acceptance, data migration reconciliation, service ownership, support commitments and tested rollback |

For paid SaaS, add plan/entitlement management, metering, invoicing through a billing provider, billing webhook reconciliation, cancellation/export and retention policy. Decide whether billing is required for launch or managed contractually; do not confuse SaaS subscription invoices with customer procurement invoices.

## 17. Deployment, migration and customer launch

### 17.1 Environments and release pipeline

- Local development: repeatable container setup and synthetic seed data; no real customer secrets.
- CI: formatting/types, targeted unit/integration checks, schema validation, security scans and image build.
- Staging: separate Cloudinary product environment plus production-like identity, queue and database behavior using sanitized fixtures.
- Production: isolated account/project, least-privilege deployment identity, managed secrets, private services and monitored ingress.
- Promote immutable artifacts through environments; record release and migration versions.
- Use backward-compatible expand/migrate/contract database changes. Destructive cleanup follows an explicit retention and recovery review.
- Test migrations on realistic volumes; define rollback or forward-fix for each stateful change.
- Feature flags permit tenant-limited rollout and disabling AI/integrations without disabling core procurement.

### 17.2 Migration and onboarding

1. Agree record ownership, scope, cutover window and source export format.
2. Validate supplier, category, cost-center and open-PO mappings in a dry run.
3. Detect duplicates, rejected rows and missing references; provide a correction report.
4. Reconcile record counts and monetary totals with source owners.
5. Import with stable external IDs and an idempotent batch identifier.
6. Configure users, approval policies, budgets, communication templates and retention.
7. Train buyer, supplier, approver, receiver, finance and support roles.
8. Run a representative purchase with supervised users.
9. Obtain recorded customer acceptance and define escalation contacts.
10. Monitor initial transactions closely and retain a documented cutover reversal procedure.

### 17.3 Required runbooks

Deployment/rollback; failed migration; database restore; provider outage; stuck job; failed email; accounting mismatch; duplicate external artifact; unauthorized access; compromised supplier; tenant export/deletion; key rotation; unexpected AI spend; model rollback; and handling an incorrect award already communicated to a supplier.

For each: trigger, severity, owner, diagnostic steps, safe remediation, verification, customer communication owner and follow-up record.

## 18. Definition of done and release gates

A feature is done only when its normal and exceptional paths work in the UI/API, permissions are enforced, data migrations exist, tests pass, audit/telemetry are present, documentation is updated, and a designated reviewer accepts its requirement criteria. No mock, manual database edit or unimplemented button can satisfy a release requirement.

### 18.1 R1 gate

- [ ] ORG identity/isolation and role boundaries verified across all supported surfaces.
- [ ] Approved requisition → RFQ → verified offers → comparison → award → PO → receipt → basic match works end to end.
- [ ] Original evidence and review history are retained and citations resolve.
- [ ] Cloudinary assets remain authenticated, signed downloads enforce current application authorization, and upload quarantine, reconciliation, restore and deletion scenarios pass.
- [ ] Critical commercial fields require confirmation; AI cannot authorize purchases.
- [ ] LangGraph checkpoint recovery, replay idempotency, interrupt authorization and stale-source scenarios pass for both R1 graphs.
- [ ] Budget, scoring and allocation calculations pass independent fixture checks.
- [ ] Approval staleness, duplicate requests, failed jobs and provider outage scenarios pass.
- [ ] Backup restore works in an isolated environment.
- [ ] No unresolved critical/high security findings affecting supported workflows.
- [ ] Pilot users, support owner, limitations, incident escalation and acceptance evidence are documented.
- [ ] Research dataset permissions, frozen evaluation split and reproducible scripts are ready.

### 18.2 R2 gate

- [ ] Every R2 requirement in Section 4 has a completed implementation and accepted test reference.
- [ ] Partial/over/under deliveries, returns, credits, disputes, amendments and cancellations reconcile correctly.
- [ ] Selected accounting connector passes sandbox and controlled production reconciliation.
- [ ] SLO/load targets are measured; alert routing and response ownership are tested.
- [ ] RPO/RTO proven through restore drill, including files and audit artifacts.
- [ ] Security review complete; no unaccepted high-impact issues remain.
- [ ] Privacy, provider handling, retention and applicable jurisdiction configuration are reviewed.
- [ ] Tenant onboarding, export, closure and deletion procedures work.
- [ ] Support documentation, release notes, known limitations and customer acceptance are complete.
- [ ] Deployment rollback/forward-fix and data migration plans are rehearsed.

Production readiness is a gate decision supported by evidence, not a scheduled date or a percentage of features completed.

## 19. Traceability and planning process

Create one tracked epic per requirement group and one or more tickets per requirement. Each ticket must contain:

```text
Requirement ID and release:
User problem and permitted actors:
Inputs and validation:
Business invariants and workflow transitions:
Normal flow and failure/recovery flows:
API/event/data changes:
Privacy, tenant boundaries and audit requirements:
UI states and accessibility:
Acceptance scenarios and test references:
Metrics/runbook/documentation changes:
Dependencies, estimate, owner and reviewer:
Release evidence and acceptance decision:
```

Maintain `docs/product/requirements-matrix.md` mapping requirement → tickets → API/screens → tests → release evidence → owner. Keep ADRs for major decisions and a risk register with owner, trigger, mitigation and contingency. Review scope, risk, cost and acceptance evidence every two weeks.

### 19.1 Main delivery risks

| Risk | Mitigation / contingency |
|---|---|
| Too broad for an FYP | One goods category and explicit R1/R2 boundary; defer expansion features |
| Weak access to real quotations | Secure permission early; use labeled synthetic cases and disclose external-validity limits |
| Extraction quality varies by format | Supported-format policy, source review, manual entry and per-format evaluation |
| Supplier risk claims lack evidence | Start with observed first-party performance; show unknowns and sample sizes |
| Approval/budget race conditions | Transactional invariants, concurrency tests and immutable snapshots |
| Provider cost/outages | Usage budgets, bounded retries, caching and manual operation |
| ERP integration takes longer than expected | Choose one connector early; ship reviewed exports for R1 and retain R2 gate |
| Multi-agent complexity has no measured benefit | Benchmark against a simpler grounded pipeline and remove unnecessary orchestration |
| Operational ownership is missing | Assign service/support owners before onboarding real customers |

## 20. First ten working days

| Day | Concrete outcome |
|---|---|
| 1 | Confirm team capacity, initial customer/category, release boundary and available infrastructure budget |
| 2 | Interview procurement/requester stakeholders; map current sourcing and approval steps |
| 3 | Interview finance/receiver/supplier stakeholders; capture exceptions and integration ownership |
| 4 | Obtain permitted sample documents and define critical-field labels and evidence rubric |
| 5 | Draft domain model, state transitions, money/budget invariants and role matrix |
| 6 | Prototype requisition, quote review, comparison and approval screens for stakeholder feedback |
| 7 | Record stack/provider ADRs, including LangChain/LangGraph boundaries, pinned-version policy, checkpoint store, threat model and processing/retention assumptions |
| 8 | Build requirement matrix and prioritize the first vertical slice |
| 9 | Establish repository, CI, container setup, initial migrations and isolated staging |
| 10 | Demonstrate authenticated tenant-scoped requisition creation with an audit event and isolation test |

## 21. Final demonstration and handover

Use the example purchase of 150 laptops within PKR 30 million as a repeatable fixture:

1. Submit the requirement and obtain budget approval.
2. Publish an RFQ and collect three supplier offers.
3. Show one unclear warranty term, one missing mandatory support requirement, and one scanned price table.
4. Review extracted values against source evidence and resolve only documented ambiguities.
5. Show deterministic eligibility and comparison; explain the distinction between a low price and an eligible offer.
6. Run single/split allocation and an infeasible deadline scenario.
7. Approve a specific award version, then demonstrate that a material edit requires renewed approval.
8. Issue a PO, record a partial receipt and flag an overbilling mismatch.
9. Show supplier isolation, a recoverable AI outage and an idempotent retry.
10. Export the decision evidence package and present measured research results with limitations.

Handover includes source code, reproducible environment, migration instructions, OpenAPI/event schemas, seed fixtures, permission matrix, data dictionary, ADRs, user/admin guides, runbooks, security review, evaluation scripts/results, release evidence and the remaining R2/R3 backlog.

## 22. Technical references

These primary references support specific design mechanisms; they do not establish that ProcureX already meets them. Recheck supported versions and provider behavior when implementing.

- [OWASP Application Security Verification Standard](https://owasp.org/projects/asvs): application security verification requirements.
- [PostgreSQL row security policies](https://www.postgresql.org/docs/17/ddl-rowsecurity.html): database access policy behavior and bypass considerations.
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence): durable checkpoints, recovery and state retention.
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts): human review pauses and resumption behavior.
- [LangChain overview](https://docs.langchain.com/oss/python/langchain/overview): model/tool integrations and the relationship between LangChain agents and LangGraph.
- [LangChain structured output](https://docs.langchain.com/oss/python/langchain/structured-output): schema-constrained model results and validation patterns.
- [OR-Tools CP-SAT](https://developers.google.com/optimization/cp/cp_solver): integer constraint solving and result statuses.
- [W3C WCAG 2.2](https://www.w3.org/TR/WCAG22/): accessibility success criteria.
- [Cloudinary upload API](https://cloudinary.com/documentation/image_upload_api_reference): signed uploads, resource types and authenticated delivery types.
- [Cloudinary media access control](https://cloudinary.com/documentation/control_access_to_media): authenticated assets and signed delivery URLs.
- [Cloudinary backups and version management](https://cloudinary.com/documentation/backups_and_version_management): backup enablement, restore and version behavior.
- [Cloudinary asset deletion](https://cloudinary.com/documentation/delete_assets): deletion APIs, CDN invalidation and backup considerations.
