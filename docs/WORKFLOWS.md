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
| Document version | Quarantined → Scanning → Parsing → Extracted → Reviewed |
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
to the revision they answered. The server rejects post-deadline quotes and premature closure.
Shared and private clarification visibility is persisted for later supplier-portal enforcement.

## Required recovery behavior

- Worker replay cannot duplicate finalized records or external actions.
- Access is rechecked before a resumed graph or sensitive side effect.
- Changed source versions make pending approval or analysis stale.
- Provider failure ends in bounded retry or an owned manual queue.
- Timeouts after external creation reconcile by stable external reference before retry.
