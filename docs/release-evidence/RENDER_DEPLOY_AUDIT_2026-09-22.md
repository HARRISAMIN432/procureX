# Render deployment audit — 2026-09-22

## Result

The repository's free Render demonstration profile is structurally deployable after the fixes in
this audit. It remains a demonstration profile and is not approved for customer production.

## Verified locally

- Render Blueprint validates against `https://render.com/schema/render.yaml.json`.
- Production settings load with empty static allowlists plus the exact Render-assigned API hostname
  and frontend URL.
- Trusted-host and CORS middleware accept those exact runtime values without a wildcard.
- The configured PostgreSQL database is already at Alembic head `20260922_0017`.
- Backend: Ruff passed, strict mypy passed, and 182 tests passed with one intentional skip.
- Frontend: ESLint and the production TypeScript/Vite build passed; npm reported no vulnerabilities.
- The default and Blueprint Gemini model are the provider-tested `gemini-3.1-flash-lite`.
- Eager tasks use unpooled async database connections so their separate event loops cannot reuse or
  dispose request-loop connections.

## Deployment controls added

- Render-assigned URLs feed the frontend API base URL, backend trusted host, CORS origin, and email
  invitation link through Blueprint service references.
- PostgreSQL is pinned to major version 17 and public database ingress is disabled.
- API and database are pinned to the same Render region.
- The free API profile uses bounded database connections and a 256 MB parser subprocess limit.
- The container build downloads ClamAV signatures and fails if the scanner is unusable.
- Graceful shutdown allowance is 60 seconds and readiness executes a real database query.

## External prerequisites not provable in the repository

The initial Blueprint form must receive valid OIDC, Cloudinary, Gemini, and Resend credentials plus
a Resend-verified custom sender. After Render assigns the frontend URL, that exact callback and
post-logout URL must be registered with the OIDC provider. A real deployed smoke test is still
required because this workstation has no Docker daemon or connected Render account.

Render's free web service sleeps, the free database expires and has no backups, and eager tasks are
not durable across process termination. Before accepting customer data, use paid persistent
PostgreSQL, a durable broker, dedicated workers, separate schema-owner/runtime database roles,
current ClamAV signature maintenance, and the remaining acceptance evidence in `P8_EXIT.md`.
