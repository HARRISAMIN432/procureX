# Hosted buyer/supplier isolation drill

Status: **not run**. No deployed URL or synthetic buyer/supplier test sessions were available in
the workspace as of 2026-09-27. Do not treat passing local tests as hosted release evidence.

After deploying the migration `20260927_0019` and the API, create one published RFQ with two
approved suppliers and distinct verified supplier contacts. Sign in as each supplier and a buyer
using three separate browser profiles. Set the following environment variables in a private shell
without placing cookies in command-line arguments, logs, or tickets:

```
PROCUREX_HOSTED_BASE_URL
PROCUREX_HOSTED_ORG_ID
PROCUREX_HOSTED_RFQ_ID
PROCUREX_HOSTED_INVITATION_A_ID
PROCUREX_HOSTED_INVITATION_B_ID
PROCUREX_HOSTED_SUPPLIER_A_ID
PROCUREX_HOSTED_SUPPLIER_B_ID
PROCUREX_HOSTED_SUPPLIER_A_COOKIE
PROCUREX_HOSTED_SUPPLIER_B_COOKIE
PROCUREX_HOSTED_BUYER_COOKIE
```

Run `cd backend && .venv/bin/python scripts/hosted_isolation_probe.py`. It performs only GETs.
The probe requires each supplier to read its own invitation, denies cross-supplier and buyer
access to supplier routes, denies supplier access to buyer RFQ detail, and checks the supplier
response contains no competing submission or private clarification. Capture the release commit,
deployment URL, test date, status-only output, and reviewer approval here. Also manually test
quote mutation and CSRF denial with synthetic data; the probe does not mutate customer records.
