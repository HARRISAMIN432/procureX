# Architecture decisions

This file is the decision index. Material decisions should later receive individual ADRs under
`docs/adr/` using status, context, decision, consequences, alternatives, and date.

| ID | Status | Decision | Consequence |
|---|---|---|---|
| ADR-001 | Accepted | Begin with a modular monolith and independently scaled workers | Preserve domain boundaries without premature distributed transactions |
| ADR-002 | Accepted | Use Python FastAPI, Pydantic, SQLAlchemy 2, PostgreSQL, and Alembic | One typed backend stack close to AI and optimization workloads |
| ADR-003 | Accepted | Use Cloudinary instead of direct S3-compatible storage | All customer assets require authenticated delivery and local authorization metadata |
| ADR-004 | Accepted | Use LangChain for AI integrations and LangGraph for durable AI workflows | Framework use stays behind ProcureX-owned interfaces and typed state |
| ADR-005 | Accepted | Keep PostgreSQL authoritative; graph checkpoints are execution state | AI orchestration cannot replace business transactions or audit history |
| ADR-006 | Accepted | Use Celery/RabbitMQ as the outer durable work boundary | LangGraph owns steps inside an AI run, not global workload scheduling |
| ADR-007 | Accepted | Enforce tenant isolation in both application code and PostgreSQL RLS | Runtime roles and connection handling require explicit safeguards |
| ADR-008 | Accepted | Use deterministic arithmetic/scoring and OR-Tools for allocation | LLMs explain evidence but do not calculate authoritative awards |

## Open decisions

- Compute cloud and deployment region.
- OIDC provider.
- OCR and primary LLM/embedding providers.
- Cloudinary plan, region, backup, retention, and residency acceptance.
- First accounting connector and exchange-rate source.
- Whether LangSmith is permitted for sanitized development traces.

