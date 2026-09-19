# ProcureX backend

Initial FastAPI/PostgreSQL foundation for ProcureX. It includes environment validation,
async SQLAlchemy models, Alembic, Cloudinary asset metadata, LangGraph run metadata,
tenant-aware database helpers, durable jobs/outbox events, and audit records.

Cloudinary upload options are generated server-side and enforce `authenticated` delivery,
`raw` resources, immutable provider IDs, and overwrite protection.

## Local setup

```bash
cp .env.example .env
docker compose up -d postgres rabbitmq redis
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Run checks with:

```bash
uv run ruff check .
uv run pytest
```

Application transactions that access tenant-owned tables must use
`tenant_transaction(organization_id)` or set the equivalent transaction-local PostgreSQL
context. Never accept the organization ID directly from an unauthenticated request body.
