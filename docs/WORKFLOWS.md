# Workflows

## End-to-end journey

1. Configure organization, roles, budgets, approval rules, categories, and retention.
2. Draft and approve a requisition with a safe budget reservation.
3. Publish an immutable RFQ version and invite suppliers.
4. Receive immutable quote versions and attachments before the server deadline.
5. Quarantine, scan, parse, extract, and review document fields.
6. Resolve hard requirements, compute deterministic comparison, and model allocation.
7. Prepare and approve an immutable award snapshot.
8. Issue idempotent POs and control amendments.
9. Record receipts, returns, invoices, and matching exceptions.
10. Reconcile accounting status and close with an evidence package.

## Initial state machines

| Object | Main states |
|---|---|
| Membership | Invited → Active → Suspended/Revoked |
| Document | Quarantined → Scanning → Ready → Archived |
| Document version | Quarantined → Scanning → Parsing → Parsed → Extracted → Reviewed |
| Analysis run | Queued → Running → Awaiting review → Completed |
| Job | Queued → Running → Completed |
| Requisition | Draft → Submitted → Approved → Sourcing → Ordered → Closed |
| Supplier | Pending → Approved → Suspended; material changes return Approved → Pending |
| Supplier qualification | Pending → Qualified/Unqualified → Expired |
| Supplier certificate | Pending → Verified/Rejected → Expired |
| RFQ | Draft → Published → Closed; Draft/Published → Cancelled |
| Invitation | Invited → Acknowledged/Submitted/No bid/Revoked |
| Quote version | Submitted → Withdrawn |
| Clarification | Open → Answered |
| Evaluation | Completed immutable version; reruns create a new version |

Failure, cancellation, retry, rejected, stale, and superseded states are explicit. Every transition
defines actor, preconditions, expected version, atomic writes, audit event, and notifications.

The currently implemented requisition transitions are create draft, replace draft/changes-requested
content, submit, approve, reject, and cancel. Submission increments the aggregate version and
writes an immutable JSON snapshot with a SHA-256 digest. An approval request binds that snapshot
to a versioned policy and dated budget. Distinct decisions accumulate until quorum; final approval
and budget reservation occur atomically. Change-request and reservation-release commands remain
for the next refinement slice.

The implemented supplier workflow creates a buyer-scoped pending profile, records contacts,
category qualifications, and certificate metadata, and separates write, qualification, and
approval permissions. Approval requires at least one non-expired qualified category. Editing an
approved profile or changing a qualification away from qualified returns the supplier to pending
review; suspension is allowed only from approved. Every mutation increments the supplier version
and writes audit/outbox evidence.

The implemented sourcing workflow creates an RFQ only from an approved requisition and copies its
controlled lines and requirements. Only approved suppliers can be selected. Publication requires
at least one invitation, creates an immutable digest-bearing revision, and moves the requisition to
`sourcing`. Amendments create new publication revisions; existing quote versions continue to point
to the revision they answered, while a new quote is rejected if its explicit revision is stale.
The server rejects post-deadline quotes and premature closure.
Invitations can be acknowledged or declined with a retained no-bid reason before the deadline;
both transitions bind to an expected RFQ version and emit audit/outbox evidence. Shared and private
clarification visibility is persisted for later supplier-portal enforcement.

The implemented document intake workflow validates declared filename, media type, size, and hash;
creates an expiring quarantined document version; and returns a signed create-only Cloudinary raw
upload request. Completion must match the reserved public ID, declared byte count, authenticated
delivery type, and valid provider signature before the asset is registered and one scan job is
queued. A clean trusted scan marks the asset verified and moves the version to `parsing`; an
infected result rejects it; a scanner error leaves it quarantined for retry. No parser, OCR, model,
or user download may consume an asset while its version is quarantined or scanning. After a clean
scan, an authorized user may request a short-lived signed URL; tenant access and asset state are
rechecked on every request and issuance is audited.

A clean scan also queues one `document.parse` job. A parser worker reports an immutable native,
OCR, or hybrid attempt using a stable result key. Identical replay is accepted without duplicate
pages or events; changed content under the same key is rejected. Failed attempts retain their error
and leave the version in `parsing` for recovery. A completed attempt must contain consecutive page
numbers and persists source labels, text, dimensions, OCR confidence, and tables before moving the
version to `parsed`. Extraction may consume only a completed parse of that version.

A structured extraction result binds to the completed parse digest and enters `awaiting_review`;
the document version becomes `extracted`. Non-missing values require same-parse page anchors, while
missing values cannot claim evidence. Reviewers verify, correct, or reject fields using optimistic
extraction revisions, and every action appends its previous/new value and reason. Finalization is
blocked while any field is unresolved or any critical field is not verified. Successful
finalization completes the analysis run and moves the document version to `reviewed`.

The P5 evaluation workflow locks a closed RFQ, checks its expected version, includes every
current submitted quote version in the RFQ currency, and requires a complete requirement matrix
for each offer. Mandatory failure makes an offer ineligible, while unresolved or not-applicable
mandatory criteria block scoring. Exact decimal landed cost and a declared price/preferred
weighting produce scores only for eligible offers. Quote attachments bind immutable document
versions to the submission. Optional check citations must traverse that binding to a verified field
in a completed extraction. The service persists the normalized comparison, deterministic summary,
and digest as a new immutable version and emits audit/outbox evidence. The `evaluation_graph`
validates the citation gate, interrupts on unresolved findings, and rejects a resume carrying a
different source digest. Outcomes are still entered by an authorized reviewer; formal waivers,
independent reviews, model-backed narrative summaries, and production checkpoint invocation remain
before the broader P5 workflow is complete.

## Required recovery behavior

- Worker replay cannot duplicate finalized records or external actions.
- Access is rechecked before a resumed graph or sensitive side effect.
- Changed source versions make pending approval or analysis stale.
- Provider failure ends in bounded retry or an owned manual queue.
- Timeouts after external creation reconcile by stable external reference before retry.
