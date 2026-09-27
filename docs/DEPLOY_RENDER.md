# Render deployment

`render.yaml` provisions a zero-cost **demonstration** web/API service and PostgreSQL database. The
web service serves React and the API on one origin so browser session cookies work. It is not a
production topology and must not hold customer procurement documents.

## Deploy the demonstration

1. Connect the repository as a Render Blueprint and review the generated `procurex-api` and
   `procurex-db` resources.
2. Supply the Blueprint's prompted OIDC issuer, audience, JWKS URL, authorization URL, token URL,
   and client secret; Cloudinary cloud name, key, and secret; a Gemini API key; and a Resend API key
   plus a sender such as
   `ProcureX <invites@your-domain.example>`. Verify that sender domain in Resend first. Use separate
   development/provider projects.
   Set `PROCUREX_GEMINI_API_KEY` as the operator's backend secret: that single key serves all
   authorized users and is never entered in a workspace or exposed as a `VITE_*` frontend variable.
3. After the Blueprint assigns its URL, register
   `<the actual procurex-api RENDER_EXTERNAL_URL>/api/v1/auth/callback` with the OIDC provider. The
   API derives that callback from Render's assigned URL. The frontend uses the backend's session
   flow and does not need OIDC client credentials. The Blueprint copies the assigned hostname/URL
   into the backend trusted host, CORS origin, and invitation link. If you add a custom domain, add
   its hostname to
   `PROCUREX_ALLOWED_HOSTS`, its HTTPS origin to `PROCUREX_CORS_ALLOWED_ORIGINS`, and update
   `PROCUREX_WEB_APP_URL`, set `PROCUREX_OIDC_REDIRECT_URI` to the custom domain's callback, and
   update the OIDC provider registration.
4. Set `PROCUREX_EMAIL_REPLY_TO` if replies should go to a monitored support inbox. Deploy. The
   free-demo start command applies Alembic migrations before starting the API. Check
   `/health/ready`, then open the service URL in a browser, sign in through OIDC, and create the
   first organization. Test login, refresh, workspace selection, and logout in that browser.
5. Create tenant roles, invite members, and assign roles through the organization endpoints. Every
   authenticated request after signup includes the selected `X-Organization-ID`.

**Separate Vercel frontend caveat:** a Vercel-hosted frontend calling the Render URL directly is a
cross-site request. The API's `SameSite=Lax` cookie will not accompany it. A Vercel deployment would
need a verified same-origin proxy or same-site custom domains and matching OIDC callback setup.
Vercel Hobby also disallows commercial use, so its free tier is for personal demos only.

The Blueprint uses eager task execution because Render does not offer free background workers.
Scan, OCR, parsing, email, and AI analysis therefore execute on the single API instance after the
originating response. The container downloads ClamAV's signed malware definitions at image build
time, and the parser receives a 256 MB process limit so it can fit beside the API on a 512 MB demo
instance. Never run multiple API instances in this mode, and redeploy regularly to refresh the
embedded malware definitions. Eager mode deliberately uses unpooled database connections because
the in-process task loop is separate from FastAPI's request loop; the broker/worker production
profile retains normal connection pooling.

The demo sets the document upload cap to 10,000,000 bytes because Cloudinary's free plan lists a
10 MB raw-file limit. The Gemini API free tier says submitted content may be used to improve its
products; use only synthetic or explicitly non-confidential demonstration material with that tier.

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
   document, notification, and AI workers with a separately maintained ClamAV signature volume;
4. use separate production OIDC, Cloudinary, model, and Resend projects with rotation procedures;
5. disable self-service signup unless plan/entitlement and abuse controls are implemented;
6. deploy the buyer and supplier web applications and complete WCAG 2.2 AA verification; and
7. execute every external drill and acceptance item in `release-evidence/P8_EXIT.md`.

Render references: [free instance limits](https://render.com/docs/free),
[Blueprint specification](https://render.com/docs/blueprint-spec), and
[health checks](https://render.com/docs/health-checks).
