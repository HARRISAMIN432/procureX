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

The initial document intake API enforces a media-type allowlist, configurable byte cap, basename
filenames, expiring signed upload parameters, an organization/version-derived create-only public
ID, `raw` resource type, `authenticated` delivery, and disabled overwrite. Upload completion checks
the reserved identity, declared size, and Cloudinary response signature before recording the asset.
The asset remains quarantined until a separately permissioned scanner reports clean. The scan
worker must independently download and verify bytes/hash before parsing; that worker integration is
not yet implemented, so the current slice is not a complete hostile-file defense.

User downloads require `documents.read`, a tenant-scoped version lookup, a post-clean-scan version
state, and a verified asset. The API returns an authenticated Cloudinary URL with a configurable
60–900 second lifetime and appends an audit event. Quarantined, scanning, rejected, missing,
deletion-pending, and deleted assets never receive a URL.

Parser/OCR results require a separate `documents.process` permission and are accepted only for a
verified asset in `parsing`. Result keys make worker replay detectable, and each successful result
is canonically digested with tenant-qualified page ownership. Parsed text and tables remain
untrusted supplier content: they do not become verified fields and must never be treated as model
instructions.

Extraction workers have `documents.process`, while human field decisions require the separate
`documents.review` permission. Worker output cannot assign verified/rejected states. Present values
must cite a page owned by the same tenant, document version, and parse; missing values cannot claim
support. Critical fields block completion unless human-verified, review updates use optimistic
revisions, and corrections retain before/after values, actor, reason, and time. Graph resume also
checks the immutable source digest to reject stale review continuation.

## AI-specific controls

Models have no purchasing authority, unrestricted database access, or arbitrary outbound network
access. Tools are allowlisted, typed, tenant-bound, and read-only unless an explicit reviewed
application command owns the mutation. Prompt text never replaces authorization or business-rule
checks.

## Secret handling

Local values live in `backend/.env`, which is ignored. Staging and production load secrets from a
managed secret store. Cloudinary API secrets, model keys, database credentials, and signing keys
must never enter logs, graph state, audit payloads, fixtures, or source control.

Development header authentication is explicitly limited to local/test configuration. Staging and
production configuration requires OIDC mode, issuer, and audience, and must not start with the
development header mechanism enabled.

The P8 HTTP-edge baseline rejects untrusted `Host` headers, allows browser cross-origin requests
only from configured exact origins, and fails deployed configuration when hosts/origins are empty
or wildcarded. Deployed browser origins must use HTTPS; debug and SQL statement logging are
disabled. Every HTTP response carries a bounded or generated `X-Request-ID`, `nosniff`, frame
denial, no-referrer, restricted browser-feature, and no-store headers. Staging and production add
HSTS, while production disables the interactive API documentation and OpenAPI routes. TLS still
terminates at the deployment edge; the edge must redirect plaintext traffic before forwarding.
Unhandled application errors are converted to a generic request-ID-bearing response. Completion
telemetry records only safe request metadata and exception class—not query strings, request bodies,
credentials, supplier content, or exception messages that may embed sensitive provider details.

Approval requests bind immutable requisition and policy versions. Distinct approvers are enforced
by a database uniqueness constraint, requester self-approval can be prohibited by policy, and the
final approver must also hold the separate `budgets.reserve` permission.

Supplier profiles, contacts, qualifications, and certificates are tenant-owned and protected by
the same API authorization and PostgreSQL RLS boundary. Write, qualification, and approval powers
are separate permissions. Banking and payment-change fields are not collected in the current
slice; adding them requires independent verification, dual review, masking, and stricter audit
controls.

RFQ publications and quote payloads are immutable digest-bearing snapshots. Tenant-qualified
foreign keys prevent cross-organization and cross-RFQ references, and the server clock controls
submission timeliness. A quote must name the invitation's current RFQ revision, preventing an
amendment from silently rebinding an in-flight submission. The current quote endpoint requires an
internal buyer-side intake permission; it must not be exposed as supplier self-service until
supplier principals, invitation credentials, object authorization, rate limits, and
competitor-data response filtering are added.

Evaluation creation and reading use separate `evaluations.run` and `evaluations.read` permissions.
Runs are restricted to closed RFQs, tenant-owned current submissions, a complete controlled
requirement matrix, and explicit scoring weights. Mandatory unknown/not-applicable outcomes fail
closed by blocking eligibility; mandatory failures cannot be scored. The immutable snapshot binds
source versions and quote digests and emits audit/outbox records. Evidence citations cross
tenant-qualified relationships and are accepted only when the source document version was
immutably attached to that quote, the extraction completed, and the cited field was human-verified.
The graph resume contract binds review to the evaluation digest so a changed source cannot silently
reuse approval of unresolved findings.
