# ProcureX — Product & Production Delivery Roadmap

v1.2 | 19 Sep 2026 | Evidence-grounded procurement & supplier intelligence software
Status: implementation blueprint; capabilities/targets planned, not implemented or measured.

## 1. Goal & scope

Turns a purchasing req into reviewed supplier award → PO → verified delivery → reconciled invoice via reliable workflows, document intelligence, deterministic comparison, constrained allocation, human authz.
Promise: **every purchasing decision is reconstructable from approved reqs, supplier submissions, eval rules, evidence, authorized actions.**
Roadmap can't guarantee completeness: each req must become tracked ticket, implementation, test, accepted capability.

### 1.1 Planning assumptions

- Customers: private-sector SMEs buying goods via competitive quotes. Initial category IT equipment; line-item schemas must allow other categories w/o workflow rewrite.
- Multi-tenant SaaS, one region, org-level data isolation. English, PKR default currency, Asia/Karachi default timezone (both configurable).
- Buyer orgs + invited suppliers. Public tendering/statutory procurement = separate expansions.
- Baseline: 4 contributors × ~15–20 h/week × 32 weeks; actual dates depend on availability/experience.
- Real supplier data needs permission. Synthetic data must be labeled; can't substantiate real-world impact claims.
- Cloudinary = selected file service behind ProcureX-owned adapter. AI/OCR/email/exchange-rate providers = replaceable adapters w/ documented data-handling terms.
- Python AI layer: LangChain (provider-neutral model/embedding/retrieval/tool/prompt/structured-output interfaces) + LangGraph (durable orchestration, human review interrupts); see §10.1.
- User selected no compute cloud, model, business integration or budget. Validate Cloudinary plan/region/limits/backup/data-handling in Phase 0 before infra spend.

### 1.2 Release boundaries

- R0 engineering foundation (internal dev): identity, tenant boundaries, delivery pipeline, domain skeleton, observability.
- R1 FYP/controlled pilot candidate (research eval, supervised trials): requisition→RFQ, verified quotes, comparison, optimization, human award, PO, basic receipts/matching; all relevant safety gates.
- R2 prod v1 (supported customer ops): complete operational workflows, returns/disputes, recovery drills, security review, onboarding, support, prod connector, recon.
- R3 enterprise (larger/regulated customers): SSO/SCIM, advanced contracts, services procurement, catalogs, more integrations, deployment options.

R1 isn't prod-ready just because demo succeeds; unfinished R2 controls stay explicit limitations. Real purchasing must use a release passing controls for its advertised scope.

### 1.3 Boundaries

ProcureX = system of record for procurement workflow + decision evidence. ERP/accounting stays authority for ledger & payment settlement when integrated; ProcureX records payment status/recon, no bank transfers in R1/R2.
Out of scope: full accounting, payroll, warehouse mgmt, lending, autonomous purchasing, universal supplier scraping, automatic legal certification. R3 contract features assist reviewers, don't declare contracts legally valid. Country-specific tax/retention/invoice/procurement rules need qualified review before claiming support.

## 2. Users, perms, separation of duties

Role: can / cannot

- Org admin: memberships, policies, integrations, settings / can't silently alter historical awards or impersonate approver.
- Requester: create requisitions, clarify, view own / can't approve own restricted spending.
- Procurement officer: RFQs, invitations, quote review, recommendation, PO prep / can't bypass mandatory approval or modify supplier originals.
- Evaluator: assigned technical/commercial eval / only assigned events + permitted sections.
- Budget owner/approver: approve/reject within delegated scope+limits / can't exceed limit or approve stale approval.
- Finance: budgets, invoice review, matching, payment-status recon / no unreviewed supplier banking-detail changes.
- Receiver: deliveries, inspections, returns / can't change PO commercial terms.
- Legal/risk reviewer: clauses, exceptions, evidence review / can't claim unverified risk signals as fact.
- Supplier admin/contributor: own profile, submit offers, acknowledge POs / no competitors, internal notes, unrelated buyer data.
- Auditor: read/export permitted history / no mutations.
- Platform operator: infra, support / no routine customer-doc access; audited, time-limited support access.

RBAC + resource-level checks (tenant, department, assignment, amount, workflow state). API enforces perms independent of UI. Users may belong to multiple orgs; each request uses one explicitly selected membership context.
Delegation has effective dates, scope, amount limits; can't create self-approval bypass. Removing user revokes sessions/integration credentials as appropriate, reassigns pending work w/ audit trail. Supplier relationships/visibility scoped to buyer org even where supplier identity is shared.

## 3. End-to-end journey

1 admin config (org, currency, cost centers, roles, budgets, approval rules, retention, categories) → 2 requester drafts requisition (lines, qty, specs, acceptable alternatives, deadline, delivery location, justification) → 3 approvers authorize request + budget reservation per policy → 4 procurement publishes versioned RFQ to invited suppliers (deadline, criteria, terms, required docs) → 5 suppliers ask questions, submit structured offers/attachments; material clarifications reach all relevant bidders → 6 uploads pass security checks; extraction yields proposed fields w/ source evidence + review status → 7 reviewers resolve ambiguities, verify critical commercial fields before offers become award-eligible → 8 system checks hard reqs, computes deterministic scores, optionally optimizes allocation across suppliers → 9 procurement prepares evidence-backed recommendation; authorized humans approve/reject exact award version → 10 POs issued, acknowledgements recorded, controlled amendments → 11 receivers record partial/full delivery, accepted/rejected qty, returns → 12 finance matches invoices to PO + accepted receipts, resolves exceptions, exports authorized records to accounting → 13 procurement closes order after obligations/exceptions resolved, w/ supplier performance + exportable audit record.
Every stage needs assigned ownership, visible status, useful empty/error states, recovery actions, notifications, permission-aware history.

## 4. Functional reqs (ID: req — acceptance evidence)

IDs = stable identifiers for tickets/tests/evidence. Unless R3, required by R2; phase plan identifies R1 subset.

### 4.1 Organization & administration

- ORG-01: onboarding, memberships, invitations, departments, cost centers, locations, categories — new org onboards w/o DB intervention.
- ORG-02: MFA for privileged users, secure recovery, session/device revocation, invitation expiry — expired/revoked access fails at API; recovery audited.
- ORG-03: versioned approval policies, thresholds, quorum, delegation, escalation, absence handling — policy simulator shows required approvers for representative requests.
- ORG-04: locale, currency, business calendar, timezone, retention, notification, AI config — changes have effective dates, preserve historical interpretation.
- ORG-05: tenant export, closure, legal hold, deletion lifecycle — deletion reaches active storage, indexes, caches, provider artifacts; backup expiry documented.
- ORG-06: usage limits, operator admin — per-tenant quotas prevent noisy-neighbor overload w/o dropping durable work.

### 4.2 Requisitions & budgets

- REQ-01: draft/save/duplicate; lines, attachments, custom category fields — qty, unit, date, money validation in API & UI.
- REQ-02: structured mandatory/preferred reqs; AI-assisted drafts — suggestions need confirmation; every mandatory req has testable criterion.
- REQ-03: approval, rejection, revision, cancellation, comments, status tracking — unauthorized/invalid transitions fail consistently.
- REQ-04: dept/project budget allocations, reservations, commitments, releases, variance — concurrent approvals can't consume same balance twice.
- REQ-05: emergency/sole-source exceptions — records justification, scope, policy reference, approval.

Budget accounting defines available/reserved/committed/consumed w/o double counting. Requisition reservation→PO commitment conversion atomic; rejection, cancellation, amendment apply corresponding ledger movements. Customer selects consumption at receipt or invoice; policy versioned.

### 4.3 Supplier onboarding & master data

- SUP-01: profiles, contacts, categories, locations, capabilities, certificates, expiry — suppliers update own permitted fields; buyer review visible.
- SUP-02: invitation, verification, approval, suspension, duplicate review, controlled merge — duplicate suggestions never auto-merge.
- SUP-03: buyer-specific qualification, approved-supplier status — suspended/unqualified suppliers can't receive awards w/o authorized exception.
- SUP-04: performance records (delivery, quality, disputes, response time, fulfilled qty) — metrics show period, sample size, exclusions, source events, correction history.
- SUP-05: sensitive payment/contact changes — bank details minimized; changes need independent verification + dual review where collected.
- SUP-06: qualification reminders, supplier corrections/appeals — expired docs create tasks; disputed adverse findings visibly contested.

### 4.4 RFQs & supplier portal

- RFQ-01: templates, lots/items, qtys, specs, delivery/commercial terms — published RFQ immutable; amendments create versions.
- RFQ-02: invitation lists, deadlines, timezone display, acknowledgements — server receipt time decides timeliness; policy defines late-offer handling.
- RFQ-03: clarification threads, attachments, fair distribution of shared answers — suppliers never see competitors' confidential messages.
- RFQ-04: structured quote forms, upload, drafts, revisions, withdrawal, alternatives — every submission has receipt + immutable version; totals reconcile.
- RFQ-05: optional sealed commercial offers, controlled bid opening — commercial data inaccessible to buyer roles/jobs until authorized opening.
- RFQ-06: deadline extensions, cancellation, no-bid, insufficient-bid workflows — amendments notify affected suppliers, invalidate impacted downstream evals.
- RFQ-07: multi-round clarification/negotiation assistance — AI creates reviewable drafts; only authorized users send supplier communications.

Clarify whether tax, freight, duties, installation, warranty, training, recurring fees, discounts are included. Capture quote validity, price breaks, MOQs, capacity, partial-award permission, payment terms, delivery assumptions. "Delivery after advance payment" must not silently become "delivery after PO."

### 4.5 Document processing & evidence

- DOC-01: PDF/image/XLSX/DOCX intake w/ explicit size/page/type limits — unsupported, malicious, password-protected, unreadable files get actionable outcomes.
- DOC-02: quarantine, malware scan, sandboxed parsing, OCR, table extraction — files can't be downloaded as trusted or parsed before required checks succeed.
- DOC-03: typed extraction of supplier, lines, amounts, currency, taxes, terms, specs — schema validation catches malformed/incomplete output.
- DOC-04: field-level provenance — each critical value links to doc version + page/bounding box or sheet/cell.
- DOC-05: review workspace (original/normalized values, correction history, unresolved queue) — users inspect source, correct fields w/o overwriting original evidence.
- DOC-06: reprocessing, dedup — reprocessing creates extraction version; reused files keep submission-specific provenance.
- DOC-07: search, authorized downloads, retention, legal hold — search/index/download perms match source perms.

Never infer absent values as zero or "compliant." Distinguish **missing, illegible, ambiguous, conflicting, not applicable, verified**. Extracted prices, qtys, currencies, tax treatment, delivery basis need human verification in R1. Later automation only for validated field classes w/ monitored error rates + approved policy.

### 4.6 Compliance, comparison, risk

- EVAL-01: req checks pass/fail/unknown/not-applicable — unknown mandatory reqs block eligibility until resolved or formally waived.
- EVAL-02: side-by-side comparison w/ landed cost + technical reqs — shows currency conversion, exclusions, assumptions, missing terms.
- EVAL-03: versioned deterministic weighted scoring — identical inputs → identical scores.
- EVAL-04: explainable supplier risk signals — each has evidence, recency, confidence/limitations, review state.
- EVAL-05: evidence-grounded summaries, doc Q&A — unsupported answers abstain; citations resolve to authorized source versions.
- EVAL-06: eval assignments, independent reviews, disagreements, conflict declarations — unresolved material disagreement/COI visible before award.
- EVAL-07: scenario comparison, sensitivity analysis — users see when changed weights/budget/delivery limits change recommendation.

Keep price, capability, observed performance, external risk separate. No delivery history = "insufficient data," not low risk/poor performance. External adverse reports need licensed/permitted sources, entity matching, timestamps, review, correction paths. Don't invent universal risk probability from arbitrary weighted signals.

### 4.7 Award & purchase orders

- AWD-01: single/split awards, allocation proposals — qtys satisfy approved demand + quote capacity.
- AWD-02: recommendation dossier, approvals, rejection, resubmission — approval binds to immutable eval/award snapshot.
- AWD-03: reapproval after material change — price, allocation, supplier, req, policy-sensitive changes invalidate affected approvals.
- AWD-04: human override w/ reason, approved exception limits — overrides can't silently bypass non-waivable controls.
- PO-01: PO generation, org numbering, PDFs, issuance — one approved issue request → one PO despite retries.
- PO-02: supplier acknowledgement, rejection, proposed changes, attachments — acceptance never silently changes approved PO terms.
- PO-03: controlled amendments, cancellations, closure — amendments adjust commitments atomically, preserve prior docs.
- PO-04: buyer-selected supplier notifications, award outcomes — no confidential competitor eval disclosed to losing bidders.

### 4.8 Delivery, invoices, contracts, monitoring

- OPS-01: partial receipts, inspections, accepted/rejected qty, delivery evidence — cumulative receipts/tolerances reconcile to PO lines.
- OPS-02: returns, replacements, shortages, damage, warranty/service claims — return links to receipt; credit/replacement & qtys tracked independently.
- OPS-03: invoice capture, duplicate detection, credit notes — duplicate vendor invoice numbers/suspicious content matches enter review.
- OPS-04: PO/receipt/invoice three-way matching w/ tolerances — price, qty, currency, tax mismatches create blocked exceptions.
- OPS-05: non-PO invoice policy, disputes — unsupported invoices explicitly rejected or routed via separate authorized exception path.
- OPS-06: accounting export, payment-status import, recon — retried exports create no duplicates; mismatches have owned resolution queue.
- OPS-07: contract repository, linked awards/POs, obligations, renewals, reminders — extracted obligations confirmed by reviewer before activation.
- OPS-08: supplier monitoring, procurement closure — closure checks unresolved deliveries, invoices, claims, obligations.

R2 contracts: uploaded executed agreements + confirmed obligations. Clause libraries, redlining, e-signature, catalogs/punchout, blanket POs, milestone services, subscription purchasing = R3, need separate workflow specs.

### 4.9 Reporting, collaboration, admin

- REP-01: dashboards — spend, open commitments, cycle time, sourcing funnel, savings, supplier concentration, late delivery, exception backlog.
- REP-02: savings distinguish negotiated price difference from realized savings; report baseline, period, calculation.
- REP-03: permission-aware CSV/XLSX/PDF exports, scheduled reports, protected download links, export audit events.
- REP-04: comments, mentions, task inbox, email/in-app notifications, preferences, escalations; delivery failures observable/retryable.
- REP-05: historical evidence package — originals, RFQ versions, corrections, scoring rules, decisions, approvals, event history.
- REP-06: support console, tenant usage, incidents, job retry controls, config history, least privilege.

## 5. UX & screens

Access: sign in, MFA, invitation acceptance, recovery, org selection. Setup: org wizard, users/roles, cost centers, policies, budgets, integrations. Buyer home: work queue, dashboards, notifications, assigned approvals. Requisitions: list/filter, create/edit, detail, budget impact, approval history. Suppliers: directory, qualification review, profile, performance, doc expiry. Sourcing: RFQ builder, invitations, clarifications, submission tracker, bid opening. Supplier portal: buyer invitations, RFQs, quote editor, uploads, receipt, PO acknowledgement. Intelligence: processing status, extraction review, evidence viewer, req matrix. Decisions: comparison, score breakdown, risk review, allocation scenarios, award approval. Operations: PO detail/amendments, receipt, return, invoice match, dispute, contract tasks. Governance: audit search/export, retention, integration failures, support, usage.

All screens need loading, empty, unauthorized, expired-session, validation, conflict, failure, retry states. Show progress for async work; preserve drafts. Keyboard-accessible controls, visible focus, labeled inputs, usable table navigation, statuses not color-only. Target WCAG 2.2 AA (https://www.w3.org/TR/WCAG22/), verified by automated + manual testing.
Money always shows currency; date/time shows timezone. Destructive actions show affected object + consequence. Critical actions return durable receipt/status so timeouts don't encourage repetition.

## 6. Architecture & technology

### 6.1 Architecture

**Modular monolith w/ independently scaled workers.** Domain boundaries from day one; microservices later only for independent scaling, release ownership, isolation.

```text
Buyer web/Supplier portal → HTTPS edge+API → identity & tenant authz → [Procurement|Suppliers|Documents|Evaluation|Orders|Finance] → PostgreSQL+outbox, Cloudinary authenticated assets → durable job broker → OCR/parser|Evaluation|Integration workers → provider adapters (LLM, OCR, email, ERP, exchange rates)
Cross-cutting: policy enforcement, audit, secrets, telemetry, backups
```

### 6.2 Baseline stack (validate in Phase 0; pin versions after compatibility/security review; record in ADRs)

- Web: Next.js + TypeScript (buyer/supplier UIs; generated API types).
- API: Python FastAPI + Pydantic (typed contracts; proximity to document/optimization workloads).
- Persistence: PostgreSQL + SQLAlchemy + Alembic (transactional state, migrations, audit references).
- Retrieval: PG full-text; pgvector if benchmarked useful (tenant-filtered hybrid evidence search).
- File storage: Cloudinary (authenticated image/raw assets, immutable original IDs, short-lived server-signed downloads).
- Jobs: Celery + RabbitMQ (durable dispatch; app-level idempotency/recovery).
- Cache/rate limits: Redis if needed (ephemeral; never authoritative approval/budget state).
- AI layer: LangChain Python (provider adapters, prompts, tools, retrieval, embeddings, Pydantic-validated structured output).
- AI orchestration: LangGraph Python (explicit state graphs, durable checkpoints, bounded retries, branching, human interrupts).
- Optimization: OR-Tools CP-SAT (integer allocation, hard constraints).
- Identity: established OIDC provider (auth, MFA, lifecycle).
- Telemetry: OpenTelemetry + managed metrics/logs/error tracking (correlated requests, jobs, model calls, business failures).
- Delivery: containers, CI/CD, IaC (reproducible staging/prod).

Start w/ managed compute, DB, Cloudinary. Kubernetes, Kafka, graph DBs, independent domain services = optional future ADRs, not prerequisites. Don't run infra just to look large.

### 6.3 Cloudinary asset policy

Selected for R1/R2. All procurement docs uploaded server-side w/ signed requests as `authenticated` assets; use `raw` resource type when exact bytes must be preserved & no media transformation needed. Default public `upload` delivery type prohibited for customer docs. New assets stay quarantined in ProcureX, unavailable to users/AI workers until separate malware + file-validation pipeline succeeds. Browser uploads, if later enabled, need narrowly scoped API-generated signed upload + same authz/type/size/format policy.
PostgreSQL authoritative for ownership/lifecycle metadata. Each `DocumentVersion` stores Cloudinary `asset_id`, `public_id`, `resource_type`, delivery type, provider version, byte count, MIME type, original content hash, upload response signature. Provider folders/tags/public IDs = organizational aids, not tenant authz boundaries. Downloads/previews need app authz then short-lived signed Cloudinary URL; never persist delivery URLs as access grants.
Create-only identifier per immutable doc version; overwrite disabled. Corrected/replaced file = new ProcureX doc version + new Cloudinary asset. Enable Cloudinary automatic backup only after retention, residency, restore, cost, deletion behavior pass Phase 0 review. Tenant deletion/legal hold must cover originals, eager derivatives, CDN invalidation, backed-up versions. Periodic reconciler detects DB records w/o provider assets & unreferenced provider assets; deletes neither automatically.

### 6.4 Repository layout

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

Domain modules own writes to their tables. Cross-domain changes go through app services in explicit transactions. Keep business rules out of web components & LLM prompts.

## 7. Data model & invariants

### 7.1 Entities

Identity: Organization, User, Membership, Role, Permission, Delegation, AccessGrant. Procurement: Requisition, RequisitionVersion, RequisitionLine, Requirement, CostCenter, Budget, BudgetEntry. Sourcing: RFQ, RFQVersion, RFQLine, Invitation, Clarification, Submission, QuoteVersion, QuoteLine. Supplier: SupplierIdentity, BuyerSupplierRelationship, Contact, Qualification, Certificate, PerformanceObservation. Documents: Document, DocumentVersion, CloudinaryAsset, ScanResult, Page, ExtractedField, EvidenceAnchor, ReviewCorrection. Intelligence: AnalysisRun, ModelInvocation, RequirementCheck, RiskSignal, ScoringPolicy, EvaluationSnapshot. Optimization: Scenario, ConstraintSet, OptimizationRun, Allocation, SolverResult. Governance: ApprovalPolicyVersion, ApprovalRequest, ApprovalDecision, Exception, AuditEvent. Operations: Award, AwardLine, PurchaseOrder, POLine, Amendment, Receipt, ReceiptLine, Return, Claim. Finance: Invoice, InvoiceLine, CreditNote, MatchResult, Dispute, AccountingExport, PaymentStatus. Contracts: ContractVersion, Obligation, Renewal, Reminder. Platform: OutboxEvent, InboxReceipt, Job, Notification, IntegrationConnection, SyncCursor, UsageRecord, LegalHold.

Every tenant-owned record carries `organization_id`; composite keys/constraints prevent cross-tenant references. Supplier submission includes buyer org + authorized supplier relationship. Store human & service actors explicitly.

### 7.2 Invariants

- Exact decimal arithmetic for prices/taxes, currency-aware rounding; never binary float for authoritative money.
- Qty stored w/ unit + allowed precision; convert only via explicit validated unit mappings.
- Preserve original currency; separately store normalized comparison values, rate source, timestamp, rounding policy.
- Timestamps in UTC; preserve business timezone & original date assumptions.
- Published RFQs, submitted quote versions, approved awards, issued POs = immutable business versions.
- Content hashes identify doc bytes; corrections/new attachments never erase originals.
- Evidence anchors reference immutable source versions + extraction coordinates.
- Approvals bind to snapshot/version digest + policy version, not mutable object ID.
- DB constraints enforce uniqueness for submission versions, PO numbers, external mappings, scoped idempotency keys.
- Optimistic concurrency protects editing; transactional locks protect budget consumption, award issuance, other competing mutations.
- Tenant-scoped delete/archive preserves required audit references, respects legal holds.
- Reporting projections rebuildable from authoritative records; disclose refresh time.

PostgreSQL RLS = defense layer alongside app authz. Runtime roles must not be superusers, table owners w/ bypass behavior, or have `BYPASSRLS`; review `FORCE ROW LEVEL SECURITY` where appropriate; test connection-pool tenant context reset. See https://www.postgresql.org/docs/17/ddl-rowsecurity.html

## 8. State machines & failure behavior

Main states → exceptional paths

- Requisition: Draft→Submitted→Approved→Sourcing→Ordered→Closed → changes requested, rejected, cancelled
- RFQ: Draft→Published→Closed→Evaluating→Awarded → amended, extended, cancelled, no valid offers
- Submission: Draft→Submitted→Under review→Verified → superseded, withdrawn, late, disqualified
- Document: Quarantined→Scanning→Parsing→Extracted→Reviewed → rejected, failed, needs manual entry
- Analysis: Queued→Running→Awaiting review→Completed → retry scheduled, failed, cancelled, stale
- Award: Draft→Pending approval→Approved→Issued → rejected, invalidated, cancelled
- PO: Draft→Approved→Issued→Acknowledged→Partially received→Received→Closed → change requested, amended, cancelled, disputed
- Invoice: Captured→Validated→Matched→Approved for export→Exported→Settled → duplicate suspected, mismatch, disputed, credited, voided

Each transition specifies allowed actors, preconditions, atomic mutations, version checks, audit event, notifications. Spec must define all permitted exceptional transitions, not just happy path. Order delivery, financial, dispute statuses may be separate dimensions (e.g. "fully received but disputed").
Mandatory failure scenarios:

- Submission/bid-close race: single server deadline, atomic receipt rule.
- Worker crash after side effect before ack: recover via business idempotency keys.
- Approval after quote/RFQ change: reject as stale, create new approval request.
- Provider timeout/malformed AI output: bounded retry, then manual workflow; never fabricate completion.
- OCR unavailable: keep originals, allow reviewed manual entry.
- Supplier withdraws/expires after recommendation: invalidate affected allocations, seek reapproval.
- PO email fails: retain issued state, expose failure, resend same version.
- Accounting accepts export but response lost: query by stable external reference before retrying creation.
- Membership revoked during job: recheck authz before sensitive side effects/download delivery.

## 9. API, events, integrations

### 9.1 API conventions

Versioned `/api/v1`, OpenAPI-generated clients. Define pagination, filters, stable sort, request IDs, structured errors, field-level validation, documented rate limits. Tenant context from authenticated membership, not untrusted body field.

```text
/organizations /memberships /policies /budgets
/requisitions /suppliers /rfqs /submissions
/documents /extractions /reviews
/evaluations /scenarios /optimization-runs /awards
/approvals /purchase-orders /receipts /returns
/invoices /disputes /contracts /reports
/audit-events /integrations /jobs
```

Explicit commands e.g. `POST /awards/{id}/submit`, `POST /purchase-orders/{id}/issue`. Idempotency on consequential creates/commands; reuse w/ different payload fails. Expected versions/ETags for updates. Long work returns `202` + job resource w/ progress, errors, authorized retry/cancel. Transitions return conflicts rather than overwriting competing changes.

### 9.2 Durable events

Persist business state + outbox entry in same DB transaction; publish w/ retry. Consumers keep inbox/dedup record, apply idempotent effects. Assume **at-least-once delivery**, not global exactly-once.
Envelope: `event_id`, `schema_version`, `organization_id`, `aggregate_id`, `aggregate_version`, `event_type`, `occurred_at`, `actor_id`, `correlation_id`, `causation_id`, minimal payload/reference.
Events: `requisition.approved`, `rfq.published`, `quote.submitted`, `document.reviewed`, `evaluation.completed`, `award.approved`, `po.issued`, `receipt.accepted`, `invoice.matched`, `integration.failed`. Handle out-of-order versions, dead-letter queues. Scheduled sweeper detects stranded outbox entries/jobs; operator replay must not duplicate external actions.

### 9.3 Integrations (R1 → R2/later)

- Email: invitations, notifications w/ delivery status → bounce/complaint handling, templates, configured authenticated domain.
- Accounting/ERP: structured export, sandbox adapter → one customer-selected prod connector, mappings, recon, support runbook.
- Currency: reviewed manual rate snapshots → approved feed w/ freshness policy, outage fallback.
- Identity: OIDC, MFA, lifecycle basics → enterprise SSO/SCIM in R3.
- Storage/OCR/AI: provider abstraction, usage accounting → data residency options, tested provider outage handling.
- External supplier signals: first-party performance → licensed sources after coverage/quality validation.
- E-signature/catalogs: outside R1 → R3, provider-specific contracts/acceptance tests.

Every connector needs secret rotation, least-privilege scopes, rate-limit handling, stable external IDs, mapping ownership, schema change detection, retries, recon, sandbox tests, disconnect procedure. Webhooks need signature verification, replay protection, dedup, constrained outbound destinations.

## 10. AI & evidence engineering

### 10.1 LangChain/LangGraph decision

Required components of AI layer. Use Python packages behind ProcureX-owned interfaces so business domain doesn't depend on framework message objects or provider-specific response formats.
**LangChain** for: chat-model/embedding provider adapters; prompt templates + versioned prompt metadata; Pydantic-backed structured output (extraction, req findings, citations, summaries); tenant-filtered retrievers over authorized doc chunks; small allowlist of read-only tools w/ typed I/O.
**LangGraph** for workflows needing branching, checkpointed recovery, human review. First two prod graphs:

1. `document_analysis_graph`: load authorized doc version → parse/OCR result → extract typed fields → validate evidence anchors + arithmetic → interrupt for critical-field review → finalize extraction version.
2. `evaluation_graph`: load immutable eval snapshot → retrieve authorized evidence → evaluate reqs → validate citations → draft grounded comparison summary → interrupt for unresolved findings → finalize analysis run.

Graph state = versioned minimal Pydantic/typed schema of IDs + derived results, not entire docs, credentials, or authoritative business objects. Every run has `organization_id`, `analysis_run_id`, `graph_name`, `graph_version`, `thread_id`, source-version digests, correlation IDs. Production PostgreSQL-backed checkpointer must preserve resumable state; in-memory checkpointing only in unit tests/local prototypes. Checkpoints inherit tenant isolation, retention, encryption, deletion rules.
Celery remains durable queue + capacity-control boundary: starts/resumes graph run, handles scheduled/provider work. LangGraph controls steps inside an AI run. PostgreSQL domain tables authoritative for docs, reviews, evals, approvals; checkpoints = execution state, can't substitute for audit log or business transactions.
Nodes small, typed, independently testable; provider calls, retrieval, parsing isolated behind injected interfaces. Node writes domain state only via idempotent app command w/ stable business key. Failed/interrupted nodes can replay, so no node may directly issue PO, send award, approve requisition, or perform unguarded external side effect.
Record supported LangChain/LangGraph versions + upgrade policy in ADR & lock file. Framework/model upgrades require graph contract tests + frozen AI eval suite before rollout. LangSmith may be evaluated for dev tracing, but prod observability must work via OpenTelemetry & must not send customer prompts/docs to third party w/o explicit approval + data-handling review.

### 10.2 Bounded pipeline

1 intake & scan immutable original → 2 parse text/tables; OCR only when necessary; retain layout coordinates → 3 extract proposed typed fields + evidence anchors → 4 deterministic validation + commercial arithmetic checks → 5 route missing/conflicting/critical fields to human review → 6 evaluate confirmed mandatory reqs w/ deterministic rules where possible → 7 retrieve only authorized, relevant evidence for semantic questions → 8 draft summaries/tradeoffs from verified fields + cited passages → 9 validate citation existence, relevance, access; mark unsupported findings unresolved → 10 persist output, provenance, model/prompt/parser versions, cost, timing, review decisions.
Req/compliance/risk "agents" = bounded nodes w/ typed I/O; no shared unrestricted tools, no recursive delegation. Stateful execution may use durable checkpoints + human interrupts; interrupted nodes may replay, so side effects must be idempotent. See https://docs.langchain.com/oss/python/langgraph/interrupts

### 10.3 Controls

- Supplier docs = untrusted data; embedded instructions can't override system rules or trigger tools.
- No model has purchasing authority, approval authority, database-wide access, or arbitrary outbound network access.
- Deterministic price arithmetic, taxes, eligibility, scoring stay outside LLM.
- Don't expose hidden reasoning; store structured findings, supporting evidence, concise explanations.
- Define provider retention/training settings, processing region, contractual perms, redaction before sending real docs.
- Cap tokens, elapsed time, retries, tool calls, cost per run & per tenant.
- Model self-reported confidence isn't accuracy guarantee; calibrate review policies on labeled held-out examples.
- Track unsupported claims, correction rates, extraction failures, drift by category/doc type.
- Model/prompt upgrades need frozen eval runs, approval, gradual rollout, rollback.
- Manual processing available when AI disabled/unavailable.
- Cache only within valid security boundaries; cache identity includes source, prompt, model, policy versions.

### 10.4 LangGraph acceptance criteria

- Killed worker resumes same graph thread from persisted checkpoint w/o duplicating finalized extraction, review tasks, analysis records.
- Interrupt exposes only authorized review payload; resumption verifies tenant, actor permission, expected source versions, graph version.
- Changed/deleted source access makes pending run stale/unauthorized rather than continuing on cached access.
- Every terminal run reports completed/failed/cancelled/stale & correlates node/model activity w/ durable app job + audit record.
- Tests cover normal routing, missing evidence, malformed structured output, bounded retry exhaustion, interrupt/resume, replayed nodes, cancellation, provider outage.
- Graph recursion, node attempts, model/tool calls, tokens, elapsed time, tenant cost capped & observable.
- No graph output becomes award, approval, PO, or payment action w/o deterministic checks + human authz defined elsewhere.

## 11. Deterministic scoring & constrained allocation

### 11.1 Eligibility precedes ranking

Filter by confirmed hard reqs, quote validity, supplier qualification, permitted exceptions before ranking. Cheap ineligible offer can't outrank eligible one. Publish scoring policy before eval; version any authorized change.
For eligible offer `i`: normalized criterion values `s_ik` (documented fixed anchors), weights `w_k`:

```text
score_i = sum_k(w_k * s_ik)
0 <= s_ik <= 100; w_k >= 0; sum_k(w_k) = 1
```

Specify ties, rounding, missing-value handling, direction of preference. Fixed anchors reduce ranking changes from adding irrelevant bidder. Show each contribution + raw value. Weight changes produce new eval; sensitivity views expose subjective tradeoffs.

### 11.2 Allocation model

Supplier `i`, item `j`:

- `x_ij`: integer units awarded, ≥0 (fractional units need explicit integer scaling).
- `y_i`: binary, supplier `i` receives any award.
- `d_j`: required units.
- `u_ij`: verified offered capacity.
- `c_ij`: normalized landed unit cost in scaled integer currency units.
- `f_i`: fixed supplier/order charge.
- `e_ij`: 1 only if offer satisfies all non-waived hard constraints, else 0.
- `m_ij`: minimum qty when offer selected; model w/ item-level binary `z_ij`.

```text
minimize sum_i,j(c_ij * x_ij) + sum_i(f_i * y_i)
sum_i(x_ij) = d_j for each item j
0 <= x_ij <= u_ij * z_ij for each offer i,j
m_ij * z_ij <= x_ij for each offer i,j
z_ij <= e_ij; z_ij <= y_i for each offer i,j
y_i <= sum_j(z_ij) for each supplier i
sum_i,j(c_ij*x_ij) + sum_i(f_i*y_i) <= B approved budget B
sum_i(y_i) <= K if a supplier-count limit applies
```

Delivery, quality, reviewed risk thresholds determine eligibility or have explicitly modeled constraints. If split awards forbidden, enforce one selected supplier per applicable lot w/ complete qtys. Set positive minimum selected qty so selected offer can't have zero allocation.
Tiered prices, tax thresholds, minimum order values, freight breaks, discounts need explicit piecewise constraints + recon vs final award totals; baseline linear unit-cost model doesn't cover them. Surplus only via configured approved tolerance w/ explicit objective treatment.
Return solver status, runtime, objective, bound/gap if available, allocations, constraint checks. Feasible timeout result must not be labeled optimal. Infeasibility returns actionable conflicting constraints; relaxation scenarios proposed separately, need approval before changing hard constraints. Independently validate solver output before it can become award. See https://developers.google.com/optimization/cp/cp_solver

## 12. Security, privacy, governance

OWASP ASVS as traceable verification baseline, targeting applicable Level 2 controls w/ documented exceptions/review evidence; testing target, not certification claim. See https://owasp.org/projects/asvs
Required controls:

- Threat model: tenant escape, supplier impersonation, document exploits, prompt injection, quote leakage, approval bypass, invoice fraud, privileged support misuse.
- TLS, encryption at rest, managed secrets, rotation, env separation, restricted service identities.
- Secure cookies/sessions, CSRF where relevant, strict CORS, output encoding, upload restrictions, SSRF protections, dependency scanning.
- Cloudinary: authenticated delivery, short-lived signed URLs after authz (§6.3); derived previews eagerly generated or otherwise protected, safe content disposition, isolated rendering.
- Malware scanning; parsers w/ network isolation, resource limits, timeouts, safe archive handling.
- Tenant filtering for tables, files, vector retrieval, caches, jobs, exports, telemetry.
- Sensitive fields masked in logs; provider payload logging disabled or explicitly redacted.
- Tamper-evident audit: restricted writers, append-only app behavior, independently retained audit exports. Hash chain alone doesn't defeat admin who can rewrite data & hashes.
- Audit record: actor, org, action, object/version, timestamp, request ID, reason, safe before/after references.
- Retention schedules by record class, legal holds, deletion verification, documented backup aging.
- Runbooks: security incident, credential compromise, leaked quote, supplier account takeover.
- Independent security review before R2, incl. cross-tenant tests + authn/authz abuse cases.
  Legal/tax reqs maintained as versioned jurisdiction configs reviewed by specialists. Don't describe app as compliant w/ a law/certification merely because controls appear here.

## 13. Reliability, performance, targets

Proposed thresholds; benchmark & approve in discovery; report exclusions & measured results.

- Availability: 99.5% monthly R1 pilot; 99.9% R2 core API/web, external probes.
- Interactive latency: p95 <500 ms ordinary reads, <1 s writes, excluding async/provider work.
- Document pipeline: p95 <3 min for defined 20-page supported fixture at target load; scanned vs native PDFs reported separately.
- Comparison: p95 <2 s deterministic comparison of 50 offers × 100 lines on benchmark hardware.
- Optimization: 30 s default budget; honest solver status; feasible candidate only if validated.
- Pilot scale: 20 tenants, 100 concurrent users, 50,000 stored docs; realistic skew + queue bursts.
- Recovery: R2 RPO ≤15 min, RTO ≤4 h, verified by restoration exercise.
- Integrity: no accepted duplicate PO issuance, unauthorized approval, cross-tenant disclosure in release tests.
- Usability: ≥80% representative pilot users complete core task w/o facilitator intervention.

Monitor: API error/latency, DB saturation, queue age, document failure rates, stuck approvals, notification delivery, provider spend, solver failures, outbox delay, connector recon gaps. Alerts need owners + runbooks; page on user impact, not every transient retry.
Use bounded queues, per-tenant quotas, worker concurrency limits, backpressure, provider circuit breakers. Reserve capacity for interactive actions so large OCR batch can't block approvals. Budget whole service: hosting, DB, Cloudinary storage/backup/transformation/bandwidth, OCR, AI, email, monitoring, support. Measure cost per RFQ & per processed doc before setting prices.

## 14. Testing & research eval

### 14.1 Software verification

- Unit/property: money, units, scoring, eligibility, allocation invariants, budget ledger, transitions.
- Integration: real PostgreSQL isolation/RLS, transactions, object perms, broker replay, migrations.
- API contract: schemas, perms, concurrency conflicts, idempotency, version compatibility.
- E2E: buyer/supplier workflows, approval changes, PO, receipt, matching, correction paths.
- Security: IDOR, tenant leakage, privilege escalation, hostile uploads, prompt injection, signed URL exposure.
- Resilience: worker death, provider outage, duplicate/out-of-order events, broker/DB restart, interrupted export.
- Performance: interactive concurrency, large quotes, doc bursts, slow tenants, optimizer limits.
- Accessibility: automated checks + keyboard/screen-reader review of essential workflows.
- Operational: backup restore, key rotation, rollback, tenant export/deletion, alert delivery.
  Critical release scenarios: two approvers competing for same budget; altered quote after approval; supplier reading competing offer; repeated PO issue request; late submission at deadline; two partial receipts against one invoice; return followed by credit; provider outage during analysis; accounting timeout after successful creation.

### 14.2 AI dataset & experiment design

Permissioned labeled starting set ~200–500 docs across 30–50 RFQ scenarios: scanned/native PDFs, spreadsheets, layout variation, currencies, conflicting terms, incomplete offers. Collection targets; confirm achievable diversity in Phase 0. Split by supplier/template/RFQ family to reduce leakage. Preserve frozen held-out set; never tune on test results.
Annotate required fields, units, line associations, source anchors, eligibility decisions, known ambiguities. Two reviewers label representative subset, measure agreement, resolve differences w/ documented rubric. Report synthetic & real-doc results separately.
Research question: **Does evidence-grounded structured procurement analysis improve eval accuracy, consistency, traceability vs manual & LLM-only eval?**
Compare: 1 manual eval w/ fixed rubric; 2 LLM-only eval of same docs; 3 structured extraction + deterministic checks + single grounded analysis pipeline; 4 optional bounded multi-agent pipeline (identical evidence, comparable resource budgets).
Measure: field accuracy, critical-field error, req classification, unsupported-claim rate, citation correctness, reviewer correction time, total task time, repeated-run agreement, cost, allocation feasibility. Use matched cases, counterbalanced task order, consistent human assistance, uncertainty intervals. Ablations for retrieval, validation, multi-agent coordination. Multi-agent orchestration = hypothesis, not guaranteed contribution.
Provisional gates on frozen set:

- ≥95% exact normalized accuracy for critical extracted fields; show per-field & scan-quality results.
- ≥98% correct supporting citations among sampled factual claims; source existence alone insufficient.
- Zero observed unsupported claims designated critical in release eval; document sample size + uncertainty.
- All uncertain critical fields still require review regardless of aggregate accuracy.
- 100% independent feasibility validation for accepted optimizer outputs.
- Any time-saving claim includes workload, participant count, baseline, confidence interval.
  If gates fail: reduce supported formats/categories, improve extraction/review, or keep feature assistive. Don't weaken purchasing controls to improve demo completion.

## 15. Delivery plan: 32-week FYP/controlled-pilot candidate

Each phase yields working vertical slices, tests, docs. Demonstrate integrated behavior every two-week iteration. Estimates = planning assumptions, not commitments.
Phase (weeks): deliverables → dependencies/exit gate

- P0 discovery (1–2): user interviews, workflow maps, category schema, scope, threat model, data perms, stack/provider ADRs, acceptance backlog → feedback from requesters, procurement, finance, suppliers; choose pilot category + success metrics.
- P1 foundation (3–5): repo, CI, dev/staging, identity, orgs, permission model, DB migrations, Cloudinary adapter + authenticated asset policy, queue, audit, telemetry; LangChain/LangGraph ADR, pinned deps, graph state/checkpoint schema, tracing scaffold → tenant isolation tests pass across API/Cloudinary assets/jobs/checkpoints; signed delivery + deletion/recon tests pass; sample graph survives worker restart in staging; reproducible setup + staging deployment.
- P2 requisition & supplier (6–8): request forms, budgets, approvals, supplier onboarding/directory → approved requisition reserves budget safely; supplier role boundaries pass.
- P3 sourcing (9–11): RFQ publishing, invitations, portal submissions, revisions, clarifications, deadlines → two suppliers submit against versioned RFQ; deadline/revision tests pass.
- P4 docs (12–15): secure upload, parsing/OCR, LangChain structured extraction, `document_analysis_graph`, evidence viewer, interrupt/resume review + correction → critical fields verifiable from originals; hostile/failed inputs safe; graph replay doesn't duplicate results.
- P5 eval (16–18): req matrix, landed cost, deterministic scores, first-party performance, authorized retrieval, `evaluation_graph` grounded summary → same verified inputs reproduce scores; unknown reqs block eligibility; citation + graph recovery gates pass.
- P6 allocation & award (19–21): solver, constraints, sensitivity, recommendation dossier, snapshot approvals → infeasible/timeout handled; changed inputs invalidate approvals.
- P7 order ops (22–24): PO issue/acknowledgement, partial receipt, basic invoice matching, accounting sandbox/export → full happy path + duplicate/retry + mismatch scenarios pass.
- P8 stabilization (25–28): security fixes, failure drills, perf tuning, accessible critical screens, backup restore, pilot onboarding → all R1 checks pass; known limitations approved for supervised pilot.
- P9 eval & handover (29–32): controlled user study, frozen benchmark, thesis/report, demo, user guides, runbooks, evidence archive → reproducible results, accepted R1 scope, prioritized R2 backlog.

Current progress: P2 includes requisition drafts/submission, versioned approval policies, quorum decisions, append-only budget reservations, first SUP-01–SUP-03 buyer-scoped supplier directory + qualification workflow. Supplier invitations/self-service, duplicate-review/merge tooling, expiry automation, sourcing eligibility enforcement remain in P2/P3 backlog, not claimed complete.
P3 has first backend vertical slice: approved-requisition RFQ creation, approved-supplier selection, immutable publication/amendment snapshots, revision-bound immutable quote versions, deadline enforcement, shared/private clarification records. Supplier portal identity + object filtering, acknowledgements/no-bid, attachments, notifications, idempotency keys, end-to-end PostgreSQL isolation tests remain before P3 exit gate.

### 15.1 Responsibilities

A: buyer UI, design system, accessibility. B: transactional API, perms, budgets, approvals, migrations. C: document pipeline, evidence, grounded analysis, research dataset. D: supplier portal, optimization, integrations, deployment automation. Second reviewer on every critical subsystem. Redistribute after measured velocity; nobody sole operator/reviewer of a prod-critical component. Product validation, security, testing shared.

### 15.2 Critical path & scope reductions

Critical path: identity/isolation → requisitions/approvals → RFQ/submission versions → verified extraction → comparison → award snapshot → PO → receipt/match → recovery/security validation.
If behind, defer external risk feeds, elaborate dashboards, multi-agent orchestration, extra file formats, extra categories. Preserve human review, access control, audit, deterministic arithmetic, idempotency, recovery. Narrower correct workflow = acceptable FYP outcome; label release scope honestly.

## 16. R2 prod completion

Separate envelope ~12–20 weeks after R1 for assumed team; re-estimate from pilot defects/unfinished reqs. Not evidence all enterprise features fit.

- Operational completeness: returns/replacements, disputes, credit notes, full amendment/cancellation rules, closure, warranty claims.
- Financial controls: tolerance policies, verified tax config, non-PO exceptions, prod accounting connector, recon.
- Contract basics: executed contract repository, confirmed obligations, renewal/reminder ownership.
- Platform operations: tenant lifecycle, quotas, support access, usage, incident handling, backup/restore, retention execution.
- Product polish: help, onboarding, imports, exports, notification preferences, accessibility remediation.
- Assurance: independent security review, realistic load tests, pilot fixes, dependency/provider review, documented residual risk.
- Customer launch: customer acceptance, data migration recon, service ownership, support commitments, tested rollback.
  Paid SaaS adds plan/entitlement mgmt, metering, invoicing via billing provider, billing webhook recon, cancellation/export, retention policy. Decide whether billing is required for launch or contractual; don't confuse SaaS subscription invoices w/ customer procurement invoices.

## 17. Deployment, migration, launch

### 17.1 Environments & pipeline

- Local: repeatable container setup, synthetic seed data; no real customer secrets.
- CI: formatting/types, targeted unit/integration checks, schema validation, security scans, image build.
- Staging: separate Cloudinary product env + prod-like identity, queue, DB behavior using sanitized fixtures.
- Production: isolated account/project, least-privilege deploy identity, managed secrets, private services, monitored ingress.
- Promote immutable artifacts across envs; record release + migration versions.
- Backward-compatible expand/migrate/contract DB changes; destructive cleanup follows retention/recovery review.
- Test migrations at realistic volumes; define rollback or forward-fix per stateful change.
- Feature flags allow tenant-limited rollout & disabling AI/integrations w/o disabling core procurement.

### 17.2 Migration & onboarding

1 agree record ownership, scope, cutover window, source export format → 2 validate supplier, category, cost-center, open-PO mappings in dry run → 3 detect duplicates, rejected rows, missing references; provide correction report → 4 reconcile record counts + monetary totals w/ source owners → 5 import w/ stable external IDs + idempotent batch identifier → 6 configure users, approval policies, budgets, communication templates, retention → 7 train buyer, supplier, approver, receiver, finance, support roles → 8 run representative purchase w/ supervised users → 9 obtain recorded customer acceptance; define escalation contacts → 10 monitor initial transactions closely; keep documented cutover reversal procedure.

### 17.3 Runbooks

Deployment/rollback; failed migration; DB restore; provider outage; stuck job; failed email; accounting mismatch; duplicate external artifact; unauthorized access; compromised supplier; tenant export/deletion; key rotation; unexpected AI spend; model rollback; incorrect award already communicated to supplier.
Each: trigger, severity, owner, diagnostic steps, safe remediation, verification, customer communication owner, follow-up record.

## 18. Definition of done & release gates

Feature done only when normal + exceptional paths work in UI/API, perms enforced, data migrations exist, tests pass, audit/telemetry present, docs updated, designated reviewer accepts req criteria. No mock, manual DB edit, or unimplemented button satisfies a release req.

### 18.1 R1 gate

- [ ] ORG identity/isolation & role boundaries verified across all supported surfaces.
- [ ] Approved requisition → RFQ → verified offers → comparison → award → PO → receipt → basic match works end to end.
- [ ] Original evidence + review history retained; citations resolve.
- [ ] Cloudinary assets remain authenticated, signed downloads enforce current app authz, upload quarantine/recon/restore/deletion scenarios pass.
- [ ] Critical commercial fields require confirmation; AI can't authorize purchases.
- [ ] LangGraph checkpoint recovery, replay idempotency, interrupt authz, stale-source scenarios pass for both R1 graphs.
- [ ] Budget, scoring, allocation calculations pass independent fixture checks.
- [ ] Approval staleness, duplicate requests, failed jobs, provider outage scenarios pass.
- [ ] Backup restore works in isolated env.
- [ ] No unresolved critical/high security findings affecting supported workflows.
- [ ] Pilot users, support owner, limitations, incident escalation, acceptance evidence documented.
- [ ] Research dataset perms, frozen eval split, reproducible scripts ready.

### 18.2 R2 gate

- [ ] Every R2 req in Section 4 has completed implementation + accepted test reference.
- [ ] Partial/over/under deliveries, returns, credits, disputes, amendments, cancellations reconcile correctly.
- [ ] Selected accounting connector passes sandbox + controlled prod recon.
- [ ] SLO/load targets measured; alert routing + response ownership tested.
- [ ] RPO/RTO proven via restore drill, incl. files + audit artifacts.
- [ ] Security review complete; no unaccepted high-impact issues.
- [ ] Privacy, provider handling, retention, applicable jurisdiction config reviewed.
- [ ] Tenant onboarding, export, closure, deletion procedures work.
- [ ] Support docs, release notes, known limitations, customer acceptance complete.
- [ ] Deployment rollback/forward-fix + data migration plans rehearsed.
      Production readiness = gate decision supported by evidence, not a date or feature-completion percentage.

## 19. Traceability & planning

One tracked epic per req group; one+ tickets per req. Ticket template:

```text
Requirement ID and release; User problem and permitted actors; Inputs and validation; Business invariants and workflow transitions; Normal flow and failure/recovery flows; API/event/data changes; Privacy, tenant boundaries and audit requirements; UI states and accessibility; Acceptance scenarios and test references; Metrics/runbook/documentation changes; Dependencies, estimate, owner and reviewer; Release evidence and acceptance decision
```

Maintain `docs/product/requirements-matrix.md`: req → tickets → API/screens → tests → release evidence → owner. Keep ADRs for major decisions; risk register w/ owner, trigger, mitigation, contingency. Review scope, risk, cost, acceptance evidence every two weeks.

### 19.1 Delivery risks (risk → mitigation/contingency)

- Too broad for FYP → one goods category, explicit R1/R2 boundary; defer expansion features.
- Weak access to real quotes → secure permission early; labeled synthetic cases; disclose external-validity limits.
- Extraction quality varies by format → supported-format policy, source review, manual entry, per-format eval.
- Supplier risk claims lack evidence → start w/ observed first-party performance; show unknowns + sample sizes.
- Approval/budget race conditions → transactional invariants, concurrency tests, immutable snapshots.
- Provider cost/outages → usage budgets, bounded retries, caching, manual operation.
- ERP integration slower than expected → choose one connector early; ship reviewed exports for R1; retain R2 gate.
- Multi-agent complexity no measured benefit → benchmark vs simpler grounded pipeline; remove unnecessary orchestration.
- Missing operational ownership → assign service/support owners before onboarding real customers.

## 20. First ten working days

1 confirm team capacity, initial customer/category, release boundary, infra budget. 2 interview procurement/requester stakeholders; map current sourcing/approval steps. 3 interview finance/receiver/supplier stakeholders; capture exceptions + integration ownership. 4 obtain permitted sample docs; define critical-field labels + evidence rubric. 5 draft domain model, state transitions, money/budget invariants, role matrix. 6 prototype requisition, quote review, comparison, approval screens for feedback. 7 record stack/provider ADRs incl. LangChain/LangGraph boundaries, pinned-version policy, checkpoint store, threat model, processing/retention assumptions. 8 build req matrix; prioritize first vertical slice. 9 establish repo, CI, container setup, initial migrations, isolated staging. 10 demo authenticated tenant-scoped requisition creation w/ audit event + isolation test.

## 21. Final demonstration & handover

Repeatable fixture: purchase of 150 laptops within PKR 30 million.
1 submit req; obtain budget approval. 2 publish RFQ; collect three supplier offers. 3 show one unclear warranty term, one missing mandatory support req, one scanned price table. 4 review extracted values vs source evidence; resolve only documented ambiguities. 5 show deterministic eligibility + comparison; explain low price vs eligible offer. 6 run single/split allocation + infeasible deadline scenario. 7 approve specific award version; show material edit requires renewed approval. 8 issue PO, record partial receipt, flag overbilling mismatch. 9 show supplier isolation, recoverable AI outage, idempotent retry. 10 export decision evidence package; present measured research results w/ limitations.
Handover: source code, reproducible env, migration instructions, OpenAPI/event schemas, seed fixtures, permission matrix, data dictionary, ADRs, user/admin guides, runbooks, security review, eval scripts/results, release evidence, remaining R2/R3 backlog.
