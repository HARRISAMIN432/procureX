# Project context

## Purpose

ProcureX turns a purchasing requirement into a reviewed supplier award, purchase order,
verified delivery, and reconciled invoice. Its defining property is traceability: a decision
must be reconstructable from approved requirements, supplier submissions, evaluation rules,
source evidence, and authorized human actions.

## Initial scope

- Multi-tenant SaaS for private-sector small and medium organizations.
- Competitive quotation workflows for IT equipment first.
- English UI, PKR default currency, and Asia/Karachi default display timezone.
- Buyer and invited-supplier experiences.
- Human authorization for requisitions, awards, POs, and financial exceptions.

Public tendering, payments, full accounting, payroll, warehouse management, autonomous
purchasing, and legal certification are out of scope for the initial releases.

## Product principles

1. Deterministic rules own money, eligibility, scoring, and allocation constraints.
2. AI proposes typed findings with evidence; it does not approve or purchase.
3. Published or approved business artifacts are immutable versions.
4. Every tenant boundary is enforced in the API, database, files, jobs, and retrieval.
5. Failure and recovery paths are first-class product behavior.

## Source-of-truth map

| Concern | Document |
|---|---|
| Product requirements and acceptance | [REQUIREMENTS.md](REQUIREMENTS.md) |
| System components and dependencies | [ARCHITECTURE.md](ARCHITECTURE.md) |
| Business concepts and invariants | [DOMAIN.md](DOMAIN.md) |
| Tables, tenancy, and migrations | [DATABASE.md](DATABASE.md) |
| HTTP and event contracts | [API.md](API.md) |
| LangChain/LangGraph behavior | [AI_SYSTEM.md](AI_SYSTEM.md) |
| State machines and operating journeys | [WORKFLOWS.md](WORKFLOWS.md) |
| Security and privacy controls | [SECURITY.md](SECURITY.md) |
| Accepted technical decisions | [DECISIONS.md](DECISIONS.md) |
| Phases and release gates | [ROADMAP.md](ROADMAP.md) |

The detailed roadmap remains the canonical implementation blueprint. Focused documents explain
the current implementation context and should be updated with the code that changes them.

