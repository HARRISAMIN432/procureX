# Customer workflow and launch audit

Reviewed 2026-09-27 against `docs/WORKFLOWS.md`, the React routes in `frontend/src/App.tsx`,
`frontend/src/pages/`, the FastAPI routes in `backend/app/api/v1/routes/`, and the local test suite.
This is a repository review, not a deployed customer acceptance test.

## Verdict

**Blocked for sale as an operated production procurement SaaS.** The backend has substantial
domain logic and 199 passing local tests. The browser now covers the early buyer and supplier
sourcing path, but evaluation through accounting still lacks complete guided screens. The free
hosting profile also lacks durable customer-data storage and jobs. No real deployment, recovery,
browser, security, or user-acceptance evidence has
been supplied. Selling source code or a clearly scoped, non-production demonstration is a separate
commercial decision; do not represent the present hosted service as production-ready.

## Workflow map

| Journey step | API / domain implementation | Buyer or supplier browser experience | Release gap |
|---|---|---|---|
| Organization, people, roles | Signup, invitations, roles, membership endpoints | Signup and admin screens exist | Hosted OIDC and invitation lifecycle unproven; role editing/removal lacks a complete UI |
| Requisition and budget | Draft, replace, submit, cancel; budget/policy/approval APIs | Multi-line and requirement create/edit, submit, policy setup, budget routing, approval inbox/decision | Hosted buyer UAT needed |
| Supplier qualification | Profile, qualification, certificate, approval APIs | Add/qualify/approve/suspend controls | Certificate review and richer contact editing lack complete UI |
| RFQ and invitations | Draft, publish, amend, invite, clarify, close, submit quote APIs | Invite/publish/amend/close, automatic invitation email with delivery status/retry, quote review and clarification responses | Real Resend delivery and hosted buyer UAT needed |
| Supplier participation | Invitation-scoped OIDC contact authorization, quote and upload APIs | Separate portal: acknowledge, decline, quote/revise/withdraw, upload, private questions | Hosted cross-supplier isolation and document-attachment drills still needed |
| Documents and extraction | Signed upload, scan, parse, download, extraction review/finalize APIs | Source-page viewer, verified-original download, cited manual staging, field decisions and finalization | Hosted hostile-file and review UAT needed; AI extraction producer remains a separate scope |
| Evaluation and award | Comparison, analysis, allocation, award preparation and approval APIs | RFQ assessment form, evaluation/award lists, allocation and approval actions | Evidence resolution, independent multi-user approval drill, and richer dossiers need UAT |
| Order, receipt, invoice | Prepare/issue/acknowledge/receive/match/exception/export APIs | Order/invoice lists, issue/receipt/return/capture/match/exception/export controls, supplier order acknowledgement | Real accounting connector and hosted UAT remain |
| Support, export, closure | Support, export, closure, after-sales APIs | Support request and JSON export | Operator procedures, final erasure, and customer-facing after-sales/closure journeys are incomplete |

An API route does not close a browser workflow. The current generic record page renders scalar
fields only, so it does not expose related versions, decisions, lines, evidence, or action controls.
The above gaps prevent a representative customer from completing the supervised acceptance scenario
in `docs/pilot/ONBOARDING.md` without developer intervention.

## Who supplies external-service credentials

| Integration | Credential source | Does a customer enter a key? | Finding |
|---|---|---|---|
| Gemini analysis | Operator's `PROCUREX_GEMINI_API_KEY` backend secret | No | One key is shared by authorized workspaces. The community plan's 25-run monthly workspace limit is now enforced and shown in Plan & support. All workspaces still share the provider's account-wide free quota. |
| Cloudinary documents | Operator's cloud name, API key, and API secret in backend secrets | No | A signed upload sends Cloudinary's public API key and bounded signature to the browser, as its client-upload API requires. The API secret stays on the server. |
| Resend invitations | Operator's backend API key and verified sender domain | No | Invitees receive email; they do not supply a Resend key. Free-plan daily/monthly limits and bounce/complaint handling need operational verification. |
| OIDC sign-in | Operator-configured provider client and server-side client secret | No | Users sign in with their identity-provider accounts. Provider choice, domain configuration, account recovery, and revocation still need hosted proof. |
| PostgreSQL, broker, cache | Operator/deployment connection credentials | No | These are infrastructure secrets, never workspace settings. The free demo uses an in-process task mode with no durable broker. |
| Billing and accounting | Manual invoicing; accounting sandbox export | No | No Stripe/payment key is requested. Real invoicing operations and a production accounting connector or explicit manual-export scope remain operator decisions. |

No customer-facing page or request schema asks for a Gemini, Cloudinary, Resend, OIDC, or payment
API key. The Cloudinary `api_key` in signed upload parameters is a public account identifier;
[Cloudinary's client-upload documentation](https://cloudinary.com/documentation/client_side_uploading)
requires it alongside the signed request and prohibits exposing the `api_secret`.

## Hosting and operational gates

1. **Vercel Hobby commercial restriction:** its current terms limit the free plan to personal,
   non-commercial use. A sold deployment cannot use that plan. Moving the frontend to a
   commercially permitted host or obtaining an eligible Vercel plan is an operator decision.
2. **Render free durability:** the free database expires after 30 days and has no managed backup;
   web services sleep and may restart; the single-process eager task profile can lose work. Render
   explicitly discourages production use of free instances. A funded or otherwise independently
   verified durable hosting design is required before taking real procurement records.
3. **Browser authentication:** the revised Render demo serves both sides on one origin. A deployed
   browser sign-in drill is still required. Vercel plus Render has a cross-site cookie problem with
   the current direct API URL and would need a verified same-origin proxy or same-site domains.
4. **Data recovery and operations:** execute database and Cloudinary restore/deletion drills; verify
   worker retries and idempotent replay; set up alerting and incident ownership; prove least-privilege
   runtime database access and a real CI run.
5. **Trust and commercial terms:** complete the selected OIDC provider's revocation/recovery drill,
   supplier isolation, accessibility and security review, legal/privacy templates, real subprocessor
   disclosures, support commitments, and customer acceptance. These require external accounts,
   named operators, and customer or reviewer participation.
6. **Free provider data and size limits:** Cloudinary's free plan lists a 10 MB raw-file maximum;
   the Render demo now caps documents at 10,000,000 bytes. Google's Gemini API free tier says
   submitted content may be used to improve its products. Confidential procurement documents and
   supplier bids need an appropriate provider configuration and customer disclosure before AI use.
7. **Shared provider capacity:** the operator's single Gemini key and Resend account serve every
   workspace. The per-workspace AI limit prevents one customer from bypassing its plan, but it is
   not an account-wide reservation. Provider rate/volume limits can still interrupt other
   customers. Resend's free plan currently lists 100 emails per day and 3,000 per month.

Provider references checked on 2026-09-27: [Vercel Hobby](https://vercel.com/docs/plans/hobby),
[Render free limits](https://render.com/docs/free),
[Cloudinary free raw-file limit](https://cloudinary.com/pricing/compare-plans), and
[Gemini API free-tier data use](https://ai.google.dev/gemini-api/docs/pricing), and
[Resend free limits](https://resend.com/pricing).

## Work completed in this review

- Added missing Render Blueprint prompts for server-side OIDC authorization, token, and
  client-secret settings. The callback derives from Render's assigned URL; deployed settings still
  reject an incomplete OIDC configuration.
- Removed unused frontend OIDC variables from the Blueprint; the frontend uses the backend session.
- Corrected the callback setup instructions and documented the cross-site cookie failure.
- Fixed Ruff violations in the newest auth migration so the backend quality gate can pass.
- Built the React app into the Render API container and served both from the same origin, removing
  the cross-site cookie problem from the free Render demonstration profile.
- Limited Render demonstration uploads to the Cloudinary free raw-file size limit.
- Enforced the existing monthly AI-run entitlement when a new analysis is queued and exposed its
  usage in the customer Plan & support screen.
- Updated CI to build the single-origin container from the repository root.
- Added verified-contact, invitation-scoped supplier APIs and a separate supplier browser portal;
  removed the old buyer-operated quote submission endpoints.
- Added buyer requisition, approval, qualification, RFQ, evaluation, allocation, award,
  order, receipt, and invoice action screens plus list endpoints.
- Added a separate supplier purchase-order acknowledgement page and removed the buyer-side
  acknowledgement endpoint.
- Added reusable multi-line requisition editor, cited evidence-review screens, and revision-aware
  supplier email delivery with retryable status and an operator-managed Resend key.
- Added a read-only hosted isolation probe in `backend/scripts/hosted_isolation_probe.py`. It is
  locally tested, but cannot be run against a deployment until a URL and three synthetic test
  identities are provided. **Hosted buyer/supplier isolation remains unverified.**

These repository changes do not clear the external and product gates above. The next meaningful
acceptance milestone is one real buyer and one real supplier completing the documented scenario in
a durable staging environment, with a successful restore and named sign-off.
