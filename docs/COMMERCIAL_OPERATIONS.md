# Commercial operations

ProcureX can be demonstrated entirely on free services. The default `community` entitlement is
provisioned for every organization with five seats, 512 MiB of document metadata/storage allowance,
25 monthly AI runs, organization export, and accounting export. Billing mode is `manual`, allowing
the operator to invoice customers without introducing a paid billing provider or storing card data.

## Plans and entitlements

Plan changes are controlled operational changes to `organization_subscriptions`; they must be
authorized by an order form and recorded in the audit log. Never silently remove access after a plan
change. A past-due organization should receive a remediation period before suspension.

## Customer lifecycle

- Administrators can export tenant records as JSON from **Plan & support**.
- Closure requires the exact confirmation phrase and creates a 30-day reversible closure window.
- Permanent erasure is an operator-run process after backup/retention/legal-hold review. Do not claim
  erasure is complete until Cloudinary assets, database records, backups, and caches are reconciled.
- Suspended and closed organizations are rejected by request authentication.

## Support and incidents

Authenticated support cases are tenant-scoped and audited. Do not request passwords, tokens, or
confidential bid contents in a case. Operators should acknowledge urgent availability or security
cases within four business hours and normal cases within one business day; these are service targets,
not a contractual SLA unless included in an executed order form.

For an incident: preserve request IDs and logs, contain access, identify affected tenants, rotate
credentials if exposure is possible, restore service, notify customers according to applicable law
and contract, and publish a blameless post-incident record.

## Privacy-preserving analytics

Use aggregate audit-event counts and timings only. Do not install third-party session replay or send
supplier names, prices, document contents, user emails, tokens, or record identifiers to analytics.

## Supported clients

Support the latest two stable releases of Chrome, Edge, Firefox, and Safari. Mobile layouts are
responsive, but procurement administration is desktop-first. Test assistive technology before
representing the product as WCAG conformant.

## Free hosting boundary

The Render free blueprint remains the supported demonstration profile. Free database expiry,
sleeping services, lack of managed backups, and absence of a durable free worker mean it is not a
production SLA profile. Customers must receive this limitation in writing until durable hosting is
funded.
