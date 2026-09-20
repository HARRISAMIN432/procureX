# Controlled-pilot onboarding

P8 prepares a supervised research pilot, not an unsupervised production launch. The pilot owner
must stop onboarding if any mandatory gate below lacks named evidence and an accepting reviewer.

## Before inviting users

- Select the pilot organization, IT-equipment category, data owner, support owner, security contact,
  and incident escalation path.
- Record permission to use every real supplier document; otherwise use visibly labeled synthetic
  fixtures. Never mix research consent with authorization to make real purchases.
- Configure a dedicated staging environment, HTTPS ingress, OIDC issuer/audience/JWKS, tenant roles,
  approval policy, budget, timezone, currency, Cloudinary product environment, queue, model budget,
  retention, and deletion owner.
- Run the locked CI pipeline, migrations, cross-tenant PostgreSQL test, dependency audit, backup
  drill, provider-outage drill, and representative allocation benchmark against the release commit.
- Complete manual keyboard and screen-reader checks for every critical UI once that UI exists.
- Review [known limitations](KNOWN_LIMITATIONS.md) with the pilot sponsor and record acceptance.

## Role-based setup

Provision separate named users for requester, procurement officer, approver/budget owner, receiver,
finance reviewer, and auditor. Do not use shared accounts. Map each OIDC subject to one active user,
grant only required organization roles, test removal/revocation, and use a separate user for
self-approval-negative tests.

Train users on uncertain fields, source evidence, mandatory-unknown blocking, award snapshots,
material-change reapproval, supplier-response states, partial receipts, invoice mismatches, and the
fact that AI text is assistive rather than purchasing authority.

## Supervised acceptance scenario

1. Create and approve a requisition with budget reservation.
2. Publish a versioned RFQ and record at least two isolated supplier submissions.
3. Process one native and one scanned quote; verify every critical commercial field against source.
4. Demonstrate a missing mandatory requirement blocking eligibility and a valid cited comparison.
5. Run and independently validate allocation, approve the immutable award, and issue one PO.
6. Record partial delivery, supplier acknowledgement, an invoice match, and a blocking mismatch.
7. Repeat an idempotent command and a stale-version command; confirm no duplicate artifact.
8. Demonstrate database/provider failure behavior and recovery without bypassing authorization.
9. Export the evidence package and reconcile object counts, monetary totals, audit events, and source
   digests.

Record participants, environment/release commit, timestamps, results, deviations, support issues,
and sponsor acceptance. A scripted backend test or developer demonstration is not user acceptance.

## Go/no-go

Go only for the explicitly demonstrated supervised scope. Stop for any tenant leak, unauthorized
approval, duplicate PO/export, unverified critical field, missing audit history, unreconciled
restore, critical/high security finding, or unavailable support owner. Document the decision,
limitations, approver, expiry/review date, and rollback/contact procedure.
