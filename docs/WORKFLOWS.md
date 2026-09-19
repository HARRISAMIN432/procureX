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

Failure, cancellation, retry, rejected, stale, and superseded states are explicit. Every transition
defines actor, preconditions, expected version, atomic writes, audit event, and notifications.

The currently implemented requisition transitions are create draft, replace draft/changes-requested
content, submit, and cancel. Submission increments the aggregate version and writes an immutable
JSON snapshot with a SHA-256 digest. Approval, budget reservation, rejection, and change-request
commands remain in the next requisition work slice.

## Required recovery behavior

- Worker replay cannot duplicate finalized records or external actions.
- Access is rechecked before a resumed graph or sensitive side effect.
- Changed source versions make pending approval or analysis stale.
- Provider failure ends in bounded retry or an owned manual queue.
- Timeouts after external creation reconcile by stable external reference before retry.
