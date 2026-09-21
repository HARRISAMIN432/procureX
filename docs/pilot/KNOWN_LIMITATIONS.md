# Controlled-pilot known limitations

Status as of 2026-09-20: **not yet accepted for pilot**.

The repository now includes a responsive buyer web application for the implemented R1 backend
surfaces. Automated accessibility checks, manual keyboard/screen-reader review, representative-user
acceptance, and a separately isolated supplier portal are still outstanding, so the P8 accessible-
critical-screen gate and end-to-end acceptance cannot yet pass. Supplier submissions and
acknowledgements remain controlled buyer-side intake rather than supplier self-service.

OIDC-backed organization signup, verified-email invitation acceptance, tenant roles, member
lifecycle APIs, and administration UI are implemented, but invitation email delivery and the
selected identity provider's staging provisioning/revocation/key-rotation drill remain outstanding.

Other open release blockers:

- document scan and parser/OCR workers are integrated, but they still require a configured
  Cloudinary account, current ClamAV signatures, production worker image, and hostile-input staging
  drill before they constitute release evidence; the evidence viewer remains absent;
- Cloudinary reconciliation, deletion, backup, and restore have not been exercised against a
  selected account and retention policy;
- the database restore CLI is non-production only and no live restore evidence exists in this
  workspace;
- CI configuration exists but has not yet produced a successful hosted run for this commit;
- production-like OIDC, HTTPS ingress, email/notifications, Celery/RabbitMQ restart recovery, and
  PostgreSQL LangGraph checkpoint recovery have not been exercised in staging;
- no representative-user accessibility, usability, security review, or pilot acceptance record
  exists;
- the allocation timing evidence is a local synthetic benchmark, not a production load test; and
- payment execution, production accounting connectors, full returns/credits/disputes, and broader
  R2 operations remain outside the controlled-pilot scope.

These are release blockers, not silently accepted risks. P8 can be marked complete only after the
evidence matrix in `P8_EXIT.md` records passing evidence and named acceptance for every gate.
