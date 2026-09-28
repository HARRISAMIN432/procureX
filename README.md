# ProcureX

ProcureX is a multi-tenant procurement and supplier intelligence platform. It takes a purchasing
request through approval, competitive sourcing, evidence-backed evaluation, award, purchase order,
delivery receipt, invoice matching, and accounting export.

The platform is designed around traceability. Requirements, supplier submissions, calculations,
evidence, approvals, and operational changes are versioned or audited so a purchasing decision can
be reconstructed later. AI produces cited analysis for human review; deterministic code remains
responsible for eligibility, money, scoring, allocation constraints, and authorization.

> **Project status:** ProcureX is a working controlled-pilot and demonstration application. The
> repository includes the buyer workspace, supplier portal, API, database migrations, background
> jobs, tests, and a free-tier Render Blueprint. Review
> [sell readiness](docs/SELL_READINESS.md) and the
> [workflow launch audit](docs/WORKFLOW_LAUNCH_AUDIT.md) before using it with customer data.

## What ProcureX supports

- **Workspace and access management:** organizations, OIDC sessions, workspace selection, member
  invitations, roles, permissions, versioned settings, and local development bootstrap.
- **Requisitions and budgets:** typed line items and requirements, immutable submission revisions,
  approval policies, quorum decisions, self-approval controls, and an append-only budget ledger.
- **Supplier management:** buyer-scoped supplier profiles, contacts, qualifications, certificates,
  approval, and suspension.
- **Competitive sourcing:** RFQ creation from approved requisitions, immutable publication and
  amendment revisions, supplier invitations, acknowledgements, no-bid responses, clarifications,
  and versioned quote submissions.
- **Secure document intake:** authenticated Cloudinary uploads, quarantine, integrity checks,
  ClamAV scanning, bounded parsing, OCR, structured extraction, evidence anchors, and human field
  review.
- **Evaluation and AI analysis:** complete requirement matrices, exact landed-cost calculations,
  deterministic weighted comparisons, verified citations, Gemini-generated narratives, and
  LangGraph human-review interrupts.
- **Allocation and awards:** OR-Tools CP-SAT allocation with capacity, minimum quantity, split
  award, supplier count, fixed cost, and budget constraints; immutable award dossiers and approval.
- **Order operations:** purchase order issue and amendment, supplier acknowledgement, partial
  receipt and return, invoice capture, two- and three-way matching, exception handling, and an
  idempotent accounting sandbox export.
- **Commercial operations:** plan entitlements, support cases, data export requests, reversible
  closure requests, and after-sales cases.

## Technology

| Area | Technology |
|---|---|
| Web application | React 19, TypeScript, Vite, React Router, TanStack Query |
| API and validation | Python 3.12, FastAPI, Pydantic |
| Persistence | PostgreSQL 17, SQLAlchemy 2, Alembic |
| Jobs | Celery, RabbitMQ, Redis |
| Documents | Cloudinary, ClamAV, pypdf, python-docx, openpyxl, Tesseract |
| AI | LangChain, LangGraph, Gemini, PostgreSQL checkpoints |
| Optimization | OR-Tools CP-SAT |
| Delivery | Docker, GitHub Actions, Render Blueprint |

See [ARCHITECTURE.md](ARCHITECTURE.md) for component boundaries, data flows, tenancy, and deployment
topologies.

## Repository layout

```text
procureX/
├── backend/
│   ├── alembic/             # Database migrations
│   ├── app/
│   │   ├── api/v1/routes/   # Versioned HTTP endpoints
│   │   ├── auth/            # OIDC, session, and supplier access
│   │   ├── core/            # Configuration, DB, email, files, HTTP controls
│   │   ├── graphs/          # LangGraph workflows
│   │   ├── models/          # SQLAlchemy domain models
│   │   ├── optimization/    # Allocation solver
│   │   ├── schemas/         # Request and response contracts
│   │   ├── services/        # Transactional application logic
│   │   └── workers/         # Celery tasks and document sandbox
│   ├── tests/
│   ├── compose.yaml         # Local PostgreSQL, RabbitMQ, and Redis
│   └── pyproject.toml
├── frontend/
│   └── src/                 # Buyer workspace and supplier portal
├── docs/                    # Product, API, data, security, and runbooks
├── .github/workflows/       # CI verification
├── ARCHITECTURE.md
├── README.md
└── render.yaml              # Free demonstration deployment
```

## Local development

### Prerequisites

- Docker with Docker Compose
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 22 and npm
- Optional for the full document pipeline: Cloudinary credentials, ClamAV, Poppler, and Tesseract
- Optional for AI analysis: a Gemini API key

### 1. Start infrastructure

From the repository root:

```bash
docker compose -f backend/compose.yaml up -d
docker compose -f backend/compose.yaml ps
```

This starts PostgreSQL on `5432`, RabbitMQ on `5672` (management UI on `15672`), and Redis on
`6379` using local development credentials.

### 2. Start the API

```bash
cd backend
cp .env.example .env
uv sync --locked --all-groups
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

The API is available at `http://localhost:8000`. In local mode, interactive API documentation is
available at `http://localhost:8000/docs`.

Check service health:

```bash
curl http://localhost:8000/health/live
curl http://localhost:8000/health/ready
```

### 3. Start the web application

In another terminal:

```bash
cd frontend
cp .env.example .env
npm ci
npm run dev
```

Open `http://localhost:4173`.

### 4. Create a local workspace

Local development uses explicit identity headers. Bootstrap the first organization:

```bash
curl -X POST http://localhost:8000/api/v1/organizations/dev-bootstrap \
  -H 'Content-Type: application/json' \
  -H 'X-Dev-Bootstrap-Key: local-development-only' \
  -d '{
    "organization_name": "Acme Limited",
    "organization_slug": "acme-limited",
    "admin_email": "admin@example.com",
    "admin_display_name": "Admin User"
  }'
```

Copy the returned `organization_id` and `user_id` into the local login screen. For direct API
requests, send them as `X-Organization-ID` and `X-User-ID` headers.

### 5. Run background workers

The API can run the core CRUD workflows without every external provider configured. Start the
queues needed for the features you are exercising:

```bash
cd backend

# Document malware scanning and parsing
uv run celery -A app.workers.celery_app:celery_app worker \
  --queues documents.security,documents.parsing --loglevel INFO

# AI evaluation analysis
uv run celery -A app.workers.celery_app:celery_app worker \
  --queues ai.evaluations --loglevel INFO

# Organization and supplier invitations
uv run celery -A app.workers.celery_app:celery_app worker \
  --queues notifications.email --loglevel INFO
```

Document upload requires Cloudinary settings. AI evaluation requires
`PROCUREX_GEMINI_API_KEY`. Email delivery requires Resend settings. The complete configuration
surface and safe defaults are documented in [`backend/.env.example`](backend/.env.example).

### Stop local services

```bash
docker compose -f backend/compose.yaml down
```

Add `--volumes` only when you intentionally want to remove the local PostgreSQL data volume.

## Configuration

Backend settings use the `PROCUREX_` prefix and are loaded from `backend/.env`. Frontend build-time
settings use the `VITE_` prefix and are loaded from `frontend/.env`.

| Concern | Key settings |
|---|---|
| Runtime | `PROCUREX_ENVIRONMENT`, `PROCUREX_DEBUG`, `PROCUREX_ALLOWED_HOSTS` |
| Browser access | `PROCUREX_CORS_ALLOWED_ORIGINS`, `PROCUREX_WEB_APP_URL` |
| Authentication | `PROCUREX_AUTH_MODE`, `PROCUREX_OIDC_*`, `PROCUREX_DEV_BOOTSTRAP_KEY` |
| Database | `PROCUREX_DATABASE_URL`, pool and readiness settings |
| Jobs | `PROCUREX_TASK_EXECUTION_MODE`, `PROCUREX_RABBITMQ_URL`, `PROCUREX_REDIS_URL` |
| Files | `PROCUREX_CLOUDINARY_*`, document size, timeout, scanner, and parser settings |
| AI | `PROCUREX_GEMINI_API_KEY`, `PROCUREX_LLM_MODEL`, checkpoint and evidence limits |
| Email | `PROCUREX_EMAIL_PROVIDER`, `PROCUREX_RESEND_API_KEY`, sender settings |
| Web | `VITE_API_URL`, `VITE_AUTH_MODE` |

Never put server credentials in a `VITE_*` variable; Vite embeds those values in browser assets.
Staging and production validate critical security settings at startup and require OIDC, HTTPS
origins, Cloudinary, Gemini, and Resend configuration.

## Verification

Run the backend checks:

```bash
cd backend
uv run ruff check .
uv run mypy app
uv run pytest -q
```

Run the frontend checks:

```bash
cd frontend
npm run lint
npm run build
npm audit --audit-level=high
```

The integration suite expects a migrated PostgreSQL database. CI applies migrations as the schema
owner and executes the suite through a separate `NOSUPERUSER NOBYPASSRLS` runtime role so row-level
security is tested under realistic privileges.

## API and health endpoints

- API base: `/api/v1`
- Local OpenAPI UI: `/docs`
- Liveness: `/health/live`
- Database readiness: `/health/ready`

Production disables the OpenAPI, Swagger UI, and ReDoc routes. Endpoint groups and payload
contracts are listed in [docs/API.md](docs/API.md).

## Security model

- Organization-owned rows carry `organization_id` and are protected by PostgreSQL row-level
  security using a transaction-local tenant context.
- The API derives tenant access from an authenticated active membership and permission set.
- Deployed browser authentication uses OIDC Authorization Code with PKCE, server-side opaque
  sessions, HttpOnly cookies, and CSRF protection.
- Uploaded files stay quarantined until their identity, length, digest, and malware verdict pass.
- Parsing runs in a resource-limited subprocess with network sockets denied.
- Supplier text and model output remain untrusted. Evidence must resolve to reviewed fields from
  documents attached to the evaluated submission.
- Audit events, immutable revisions, stable digests, and idempotency keys preserve traceability.

Read [docs/SECURITY.md](docs/SECURITY.md) for the full threat model and controls.

## Deployment

The production Dockerfile builds the React application, installs the locked Python dependency
graph, bundles the frontend into FastAPI, installs document-processing tools, and runs as a
non-root user. Build it from the repository root:

```bash
docker build -f backend/Dockerfile -t procurex .
docker run --env-file backend/.env -p 8000:8000 procurex
```

[`render.yaml`](render.yaml) provides a free single-service demonstration topology. It uses a free
PostgreSQL database and eager in-process tasks because free Render workers are unavailable. This
profile has cold starts, expiring database storage, no managed backups, and limited memory; it is
for synthetic demonstrations only. Follow [docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md) and use
the production topology in [ARCHITECTURE.md](ARCHITECTURE.md) for customer workloads.

## Documentation

| Document | Purpose |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System structure, boundaries, runtime flows, and deployment |
| [docs/PROJECT.md](docs/PROJECT.md) | Product purpose, scope, and principles |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | Requirement groups and implementation status |
| [docs/DOMAIN.md](docs/DOMAIN.md) | Business concepts and invariants |
| [docs/DATABASE.md](docs/DATABASE.md) | Tables, tenant isolation, migrations, and recovery |
| [docs/API.md](docs/API.md) | HTTP conventions and endpoint reference |
| [docs/AI_SYSTEM.md](docs/AI_SYSTEM.md) | Graphs, evidence policy, model boundaries, and evaluation |
| [docs/WORKFLOWS.md](docs/WORKFLOWS.md) | State machines and user journeys |
| [docs/SECURITY.md](docs/SECURITY.md) | Threat model and security controls |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Accepted technical decisions |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Delivery plan and release gates |
| [docs/COMMERCIAL_OPERATIONS.md](docs/COMMERCIAL_OPERATIONS.md) | Plans, support, lifecycle, and operations |
| [docs/DEPLOY_RENDER.md](docs/DEPLOY_RENDER.md) | Free demonstration deployment guide |

Operational runbooks live in [`docs/runbooks/`](docs/runbooks/).

## Current boundaries

ProcureX is not a payment processor, accounting system, public tendering portal, warehouse
management system, or autonomous purchasing agent. Billing remains manual. Before a commercial
launch, complete the external provider drills, accessibility verification, production backups and
restore rehearsal, durable worker deployment, monitoring, and remaining release evidence tracked
in the readiness documents.

## License

No open-source license is currently included. Unless a license is added, the repository remains
all rights reserved by its owner.
