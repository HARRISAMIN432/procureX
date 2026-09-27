# ProcureX web

The frontend is a React/TypeScript procurement workspace connected to the tenant-scoped FastAPI
contract. In deployed environments, the backend performs OIDC Authorization Code + PKCE and the
frontend uses an opaque HttpOnly session cookie. Provider tokens and client secrets are never
stored in browser JavaScript. Local development headers remain available in development mode.

```bash
cp .env.example .env
npm install
npm run dev
```

For local access, bootstrap an organization through the backend and enter the returned organization
and user UUIDs on the local login screen. For OIDC, set `VITE_AUTH_MODE=oidc`, configure the OIDC
provider only in the backend environment, and register the backend `/api/v1/auth/callback` URL.
The Render demonstration image bundles this frontend with the API on one origin; its production
build sets `VITE_AUTH_MODE=oidc` and uses the browser's current origin as its API URL. A separate
frontend host must provide same-origin proxying or same-site domains for the session cookie.

Production validation:

```bash
npm run build
npm run lint
npm audit --audit-level=high
```
