# Security and privacy

## Trust boundaries

Threat modeling covers tenant escape, supplier impersonation, hostile files, prompt injection,
quotation leakage, approval bypass, invoice fraud, signed-URL leakage, and privileged support
misuse. OWASP ASVS Level 2 is the intended verification baseline, with documented exceptions.

## Required controls

- OIDC identity, MFA for privileged roles, session revocation, and expiring invitations.
- API authorization plus PostgreSQL RLS for every tenant table.
- TLS, managed secrets, least-privilege service identities, and environment separation.
- Cloudinary `authenticated` assets and authorization before short-lived signed delivery.
- Upload quarantine, malware scanning, safe type/size limits, and isolated previews.
- Network-isolated parsers with resource and archive limits.
- Tenant-scoped retrieval, caches, background jobs, exports, and telemetry.
- Sensitive-value redaction and disabled provider payload logging by default.
- Append-only application audit behavior with independently retained exports.
- Retention, legal holds, verified deletion, and documented backup aging.

## AI-specific controls

Models have no purchasing authority, unrestricted database access, or arbitrary outbound network
access. Tools are allowlisted, typed, tenant-bound, and read-only unless an explicit reviewed
application command owns the mutation. Prompt text never replaces authorization or business-rule
checks.

## Secret handling

Local values live in `backend/.env`, which is ignored. Staging and production load secrets from a
managed secret store. Cloudinary API secrets, model keys, database credentials, and signing keys
must never enter logs, graph state, audit payloads, fixtures, or source control.

