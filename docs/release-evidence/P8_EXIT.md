# P8 stabilization exit evidence

Status as of 2026-09-21: **BLOCKED — do not mark P8 complete or onboard a pilot**.

| Gate | Status | Current evidence / required closure |
|---|---|---|
| Locked static/unit suite | Pass locally | Ruff, strict Mypy, 160 tests passed; one PostgreSQL test skipped |
| Dependency vulnerability scan | Pass locally | `uv audit --preview-features audit-command`: no known vulnerabilities after pytest upgrade |
| Production identity implementation | Implemented, staging proof pending | Asymmetric OIDC/JWKS verification, verified-email invitation acceptance, self-service org bootstrap, tenant roles/member lifecycle and tests; exercise selected provider, revocation, key rotation |
| Cross-tenant PostgreSQL/RLS | CI configured, not proven | Hosted CI must migrate PostgreSQL under owner and pass tests under `NOSUPERUSER NOBYPASSRLS` role |
| HTTP security/failure behavior | Pass locally | Host/CORS, headers, safe errors, readiness timeouts, structured telemetry tests |
| Allocation performance | Pass for local fixture | [benchmark evidence](p8-allocation-benchmark.md); repeat on release hardware/load |
| Database backup restore | Tool/runbook only | Execute isolated restore, reconciliation, RLS checks; record RPO/RTO |
| Cloudinary recovery/deletion | Blocked | Select account/policy; implement and exercise reconciliation, restore, deletion/CDN invalidation |
| Document hostile-input pipeline | Partial | Scan and parse jobs dispatch, re-verify bytes/SHA-256, run bounded ClamAV, and isolate parser/OCR with seccomp plus resource/archive limits; real Cloudinary/ClamAV hostile staging fixtures remain |
| Worker/provider recovery | Blocked | Staging evidence for broker restart, model outage, checkpoint resume, idempotent replay |
| Accessible critical screens | Partial | Responsive buyer workspace implemented; run automated checks plus manual keyboard/screen-reader and representative-user WCAG 2.2 AA review; supplier self-service portal remains |
| Pilot onboarding/acceptance | Prepared, not accepted | Use pilot onboarding checklist; name owners/users and retain completed supervised scenario evidence |
| Security review | Blocked | Independent review and remediation/acceptance of critical/high findings required |
| Known limitations approval | Draft only | Pilot sponsor and service/security owners must sign and date the supported scope |

Repository-controlled stabilization now includes fail-closed deployed configuration, OIDC token
verification, safe request telemetry/errors, bounded readiness, database backup tooling, recovery
runbooks, performance tooling, a locked CI workflow with real PostgreSQL, dependency audit, and a
non-root production container. Those controls are necessary but do not substitute for external
service drills, UI/accessibility evidence, independent review, or human acceptance.

The 2026-09-21 review also removed tenant-accessible scan/parser result mutation endpoints. Those
trusted state transitions are now worker-internal, closing an administrator quarantine-bypass and
evidence-forgery path. A free Render demonstration blueprint exists, but its documented platform
limits do not satisfy the production, recovery, or worker gates above.
