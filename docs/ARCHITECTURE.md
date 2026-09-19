# Architecture

## Style

ProcureX starts as a modular monolith with independently scaled workers. Domain modules own their
tables and business rules. Cross-domain mutations run through explicit application services and
transactions rather than direct table access.

```text
Buyer web / Supplier portal
            |
       FastAPI edge
            |
 Identity + tenant authorization
            |
 Procurement | Suppliers | Documents | Evaluation | Orders | Finance
            |                  |
 PostgreSQL + outbox      Cloudinary authenticated assets
            |
     RabbitMQ / Celery workers
            |
 Documents | LangGraph AI | Integrations

Cross-cutting: audit, policy, secrets, OpenTelemetry, backups
```

## Baseline stack

| Layer | Choice |
|---|---|
| Web | Next.js and TypeScript |
| API | Python, FastAPI, Pydantic |
| Persistence | PostgreSQL, SQLAlchemy 2, Alembic |
| Files | Cloudinary authenticated assets behind a local adapter |
| Work dispatch | Celery and RabbitMQ |
| Ephemeral cache/limits | Redis when needed |
| AI components | LangChain Python |
| AI orchestration | LangGraph Python with PostgreSQL checkpoints |
| Optimization | OR-Tools CP-SAT |
| Telemetry | OpenTelemetry and managed backends |

## Backend layout

```text
backend/
├── app/
│   ├── core/          # settings, database, telemetry, security primitives
│   ├── db/            # declarative base and shared persistence helpers
│   ├── models/        # SQLAlchemy persistence models by context
│   ├── api/           # HTTP routers and request dependencies
│   ├── services/      # application commands and queries
│   └── workers/       # document, AI, and integration execution
├── alembic/           # schema revisions
└── tests/             # unit, integration, security, and contract tests
```

## Boundaries

- PostgreSQL is authoritative for business state and authorization metadata.
- Cloudinary stores file bytes and derivatives, never authorization decisions.
- RabbitMQ delivers work at least once; handlers must be idempotent.
- LangGraph checkpoints execution state, not approvals or authoritative documents.
- Provider SDK types stop at adapters and do not leak into domain objects.

