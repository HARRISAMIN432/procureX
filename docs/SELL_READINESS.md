# ProcureX sell-readiness status

Last reviewed: 2026-09-21

## Current verdict

**The repository implementation is not fully complete and ProcureX is not yet ready to operate as
a production SaaS with real paying-customer procurement data.**

It is ready for local development, product demonstrations, and a supervised non-production trial
using synthetic or non-sensitive data. The Render free deployment is a demonstration profile, not a
production service profile.

## Completed in the repository

- Multi-organization identity, membership, roles, permissions, and PostgreSQL row-level isolation.
- OIDC/JWKS authentication and verified-email organization signup.
- Responsive buyer application with permission-aware navigation.
- Requisitions, budgets, approvals, suppliers, RFQs, quotations, evaluations, allocations, awards,
  purchase orders, receipts, invoices, matching, and accounting-export backend foundations.
- Private document upload, integrity verification, malware-scan and parsing foundations.
- Human approval boundaries around awards, orders, and procurement decisions.
- Audit events, transactional outbox records, request correlation, safe errors, and security headers.
- Free community entitlement, seat and storage limits, manual billing mode, usage display, support
  cases, organization data export, reversible closure, and after-sales case records.
- Legal, privacy, DPA, subprocessor, support, incident, and commercial-operation templates.
- Free-tier Render demonstration blueprint and single-instance API rate limiting.
- Local verification: Ruff, strict Mypy, frontend lint/build, 164 backend tests, and dependency audits.

## Required before a controlled pilot

- Deploy a staging environment and record a successful hosted CI run using PostgreSQL under the
  least-privilege runtime role.
- Configure and exercise the selected OIDC provider, including invitation acceptance, revocation,
  key rotation, and account recovery.
- Implement invitation email delivery and user-facing notification delivery/retry behavior.
- Finish complete buyer workflow screens. Evaluations, awards, orders, invoices, approvals,
  document review, and after-sales operations still rely partly on generic records, UUID lookup, or
  backend-only APIs.
- Build a separately authenticated and tenant-isolated supplier portal for invitations, quotes,
  clarifications, documents, and order acknowledgement.
- Exercise real Cloudinary upload/download/reconciliation/deletion and current ClamAV hostile-file
  fixtures. Add the document evidence viewer and extraction-review experience.
- Exercise job retries, broker restart, model outage, checkpoint recovery, and idempotent replay.
- Run automated accessibility checks plus manual keyboard and screen-reader review.
- Add frontend component and browser end-to-end tests for critical workflows.
- Perform a database restore drill and record recovery time, recovery point, reconciliation, and RLS
  verification.
- Complete an independent security review and remediate or formally accept all critical/high risks.
- Complete representative-user usability testing and retain signed pilot acceptance.

## Required before selling as production SaaS

- Move customer data off the Render free database. The free database expires, has limited capacity,
  and has no managed backups. A free deployment may remain available for demonstrations.
- Run the API without idle sleep and operate durable worker/queue infrastructure.
- Add production monitoring, uptime checks, error alerting, capacity alerts, and an incident contact.
- Separate schema-migration and runtime database credentials and prove least-privilege deployment.
- Implement durable rate limiting if the service runs on more than one API instance.
- Complete final tenant erasure across PostgreSQL, Cloudinary, caches, exports, and retained backups,
  including legal-hold and retention handling.
- Select and verify a production accounting connector, or explicitly contract manual export as the
  supported scope.
- Decide whether subscriptions remain manually invoiced or integrate a payment provider. Manual
  invoicing is supported by the current repository and avoids a paid billing dependency.
- Replace legal placeholders with the operator's legal entity, jurisdiction, contacts, regions,
  retention schedule, subprocessors, commercial terms, and counsel-approved documents.
- Define and publish supported plans, pricing, taxes, refund/cancellation rules, support hours,
  service targets, and an executed customer order form.
- Establish customer onboarding, support ownership, vulnerability intake, incident response, and
  offboarding procedures with named people.

## Free-tier decision

The project will keep `render.yaml` free-tier compatible for demos. This satisfies the requirement
to have a no-cost demonstration environment, but it does not close production availability, backup,
recovery, or durability gates. Do not promise an SLA or store customer production records on that
profile.

## Definition of complete

ProcureX can be marked **pilot-ready** only when every item in the controlled-pilot section has
passing evidence and the P8 exit matrix is updated from `BLOCKED` to `PASS` with named acceptance.

ProcureX can be marked **sell-ready** only after the production-SaaS items are also complete, the
legal/commercial documents are approved, and at least one representative customer successfully
finishes the complete requisition-to-receipt-and-invoice workflow in a production-like environment.

Until then, describe the product as a **professional demonstration or technical alpha**, not as a
production-ready procurement SaaS.
