# Render deployment

`render.yaml` provisions a zero-cost **demonstration** web application, API, and PostgreSQL database. It is a
convenient way to exercise ProcureX with synthetic data; it is not a production topology and must
not hold customer procurement documents.

## Deploy the demonstration

1. Connect the repository as a Render Blueprint and review the generated `procurex-web`,
   `procurex-api`, and `procurex-db` resources.
2. Supply the Blueprint's prompted secrets: OIDC issuer, audience and JWKS URL; Cloudinary cloud
   name, key and secret; a Gemini API key; and a Resend API key plus a sender such as
   `ProcureX <invites@your-domain.example>`. Verify that sender domain in Resend first. Use separate
   development/provider projects.
3. Set the frontend OIDC authority and client ID. Register
   `https://procurex-web.onrender.com/auth/callback` with the provider. If Render changes either
   service slug, update `VITE_API_URL`, `PROCUREX_ALLOWED_HOSTS`, and
   `PROCUREX_CORS_ALLOWED_ORIGINS` to the actual HTTPS hostnames.
4. Set `PROCUREX_EMAIL_REPLY_TO` if replies should go to a monitored support inbox. Deploy. The
   free-demo start command applies Alembic migrations before starting the API. Check
   `/health/ready`, then create the first organization through `POST /api/v1/organizations` with an
   OIDC access token whose verified email matches `admin_email`.
5. Create tenant roles, invite members, and assign roles through the organization endpoints. Every
   authenticated request after signup includes the selected `X-Organization-ID`.

The Blueprint uses eager task execution because Render does not offer free background workers.
Scan, OCR, and parsing therefore execute on the single API instance after upload completion. Never
run multiple API instances in this mode.

## Free-tier limitations

As of 2026-09-21, Render documents these constraints:

- free web services sleep after 15 idle minutes and can take about a minute to wake;
- the workspace receives 750 free instance-hours per month;
- free PostgreSQL is limited to 1 GB, has no backups or managed pooling, and expires after 30 days;
- free Key Value is in-memory and loses data on restart;
- free background workers are unavailable; and
- the service filesystem is ephemeral.

These properties conflict with ProcureX's durable jobs, backup/restore, availability, and customer
data requirements. “Free for everything” can support a portfolio demo, not a professional paid
SaaS guarantee.

## Minimum customer-production changes

Before onboarding a paying customer:

1. use non-expiring PostgreSQL with automated backups and a tested restore;
2. run migrations with an owner credential and the API with a distinct `NOSUPERUSER NOBYPASSRLS`
   runtime role;
3. set `PROCUREX_TASK_EXECUTION_MODE=broker`, provision durable RabbitMQ/Redis, and deploy dedicated
   document and AI workers;
4. use separate production OIDC, Cloudinary, model, and Resend projects with rotation procedures;
5. disable self-service signup unless plan/entitlement and abuse controls are implemented;
6. deploy the buyer and supplier web applications and complete WCAG 2.2 AA verification; and
7. execute every external drill and acceptance item in `release-evidence/P8_EXIT.md`.

Render references: [free instance limits](https://render.com/docs/free),
[Blueprint specification](https://render.com/docs/blueprint-spec), and
[health checks](https://render.com/docs/health-checks).
