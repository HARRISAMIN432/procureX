# Controlled-pilot known limitations

Status as of 2026-09-20: **not yet accepted for pilot**.

The repository currently provides backend APIs and workers only. There is no buyer or supplier web
application, so the P8 accessible-critical-screen gate and end-to-end user acceptance cannot pass.
Supplier submissions and acknowledgements remain controlled intake APIs rather than a proven,
isolated supplier portal.

Other open release blockers:

- parser/OCR execution and an evidence viewer are not integrated; the new byte/hash-verifying
  ClamAV worker still requires a configured Cloudinary account, scanner image, and hostile-input
  staging drill before it is release evidence;
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
