# Local integration verification — 2026-09-22

This record documents live development checks against the providers configured in `backend/.env`.
It is engineering evidence, not production or pilot acceptance.

## Passed

- Applied Alembic revision `20260922_0016` to the configured Neon PostgreSQL database.
- Created a temporary organization through the HTTP API, resolved RBAC/tenant context, read the
  organization, membership, roles, members, initial settings, community-plan overview, support,
  after-sales, requisition, budget, supplier, RFQ, and document collections, then created and read
  back a requisition. All 17 checks returned their expected 200/201 status.
- Removed the exact temporary organization and user after the test.
- Uploaded `sample.jpeg` to Cloudinary through the same SHA-256 signed browser-style request used
  by the product, verified the returned response signature and exact reserved public ID, then
  deleted the asset successfully.
- Generated a schema-validated comparison through `gemini-3.1-flash-lite`; all returned citations
  were limited to the supplied evidence anchor.
- Connected to RabbitMQ and the dedicated LangGraph checkpoint PostgreSQL URL.
- Scanned `sample.jpeg` using the configured ClamAV command; result was clean.

## Defects found and corrected

- New organizations did not receive an initial settings version.
- Cloudinary raw uploads appended a file extension that did not match the reserved public ID.
- Boolean upload parameters used a browser wire encoding that did not match Cloudinary signature
  canonicalization.
- The configured Gemini preview model had been retired, and the full generated schema exceeded the
  provider's accepted request complexity.
- The Redis result-backend client dependency was absent from the locked runtime graph.

## Still blocked

- The configured Redis hostname does not resolve from this environment. The client dependency is
  now installed, but a valid reachable `PROCUREX_REDIS_URL` is required before Celery result-backend
  recovery can pass.
- The environment remains in `dev_headers` auth mode and has no configured frontend OIDC client.
  Provider login, MFA, invitation acceptance, logout/revocation, recovery, and JWKS rotation cannot
  be exercised until a real OIDC tenant and browser client are supplied.
- This check does not replace the hostile-file suite, browser E2E/accessibility suite, least-
  privilege RLS deployment test, backup restore drill, durable worker restart test, security review,
  or representative-customer acceptance required by `SELL_READINESS.md`.
