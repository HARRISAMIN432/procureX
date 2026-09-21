# ProcureX web

The frontend is a React/TypeScript procurement workspace connected directly to the tenant-scoped
FastAPI contract. It supports generic OIDC Authorization Code + PKCE in deployed environments and
the backend's explicit development headers locally.

```bash
cp .env.example .env
npm install
npm run dev
```

For local access, bootstrap an organization through the backend and enter the returned organization
and user UUIDs on the local login screen. For OIDC, register the frontend origin and
`/auth/callback` URL with the selected provider, then configure the `VITE_OIDC_*` values.

Production validation:

```bash
npm run build
npm run lint
npm audit --audit-level=high
```
