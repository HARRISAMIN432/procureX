import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { Session, Workspace } from "../types";
import { API_URL } from "../lib/api";

const STORAGE_KEY = "procurex.session";
const SIGNUP_KEY = "procurex.signup";
const authMode = (import.meta.env.VITE_AUTH_MODE || "dev") as "dev" | "oidc";
type BrowserSession = { authenticated: boolean; display_name: string; organization_id: string | null; csrf_token: string; workspaces: Workspace[] };
type AuthValue = { session: Session | null; ready: boolean; authenticated: boolean; workspaces: Workspace[]; authMode: "dev" | "oidc"; loginDev: (organizationId: string, userId: string, displayName: string) => void; loginOidc: () => Promise<void>; signupOidc: (details: SignupDetails) => Promise<void>; completeOidc: () => Promise<void>; logout: () => Promise<void>; selectOrganization: (id: string) => Promise<void>; refreshWorkspaces: () => Promise<void> };
export type SignupDetails = { organizationName: string; organizationSlug: string; adminEmail: string; adminDisplayName: string; defaultCurrency: string; timezone: string };
const AuthContext = createContext<AuthValue | null>(null);

function storedSession(): Session | null { try { const raw = sessionStorage.getItem(STORAGE_KEY); return raw ? JSON.parse(raw) as Session : null; } catch { sessionStorage.removeItem(STORAGE_KEY); return null; } }
async function fetchBrowserSession(): Promise<BrowserSession> { const response = await fetch(`${API_URL}/api/v1/auth/session`, { credentials: "include", headers: { Accept: "application/json" } }); if (!response.ok) throw new Error("Your sign-in session is missing or expired."); return response.json() as Promise<BrowserSession>; }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => authMode === "dev" ? storedSession() : null);
  const [ready, setReady] = useState(authMode === "dev");
  const [authenticated, setAuthenticated] = useState(authMode === "dev" && Boolean(session));
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const apply = (value: BrowserSession) => { setAuthenticated(value.authenticated); setWorkspaces(value.workspaces); setSession(value.organization_id ? { mode: "oidc", organizationId: value.organization_id, displayName: value.display_name, csrfToken: value.csrf_token } : null); };
  const refreshWorkspaces = async () => { apply(await fetchBrowserSession()); };
  useEffect(() => { if (authMode !== "oidc") return; fetchBrowserSession().then(apply).catch(() => { setAuthenticated(false); setSession(null); setWorkspaces([]); }).finally(() => setReady(true)); }, []);
  useEffect(() => { if (authMode === "dev" && session) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session)); else if (authMode === "dev") sessionStorage.removeItem(STORAGE_KEY); }, [session]);
  const value: AuthValue = {
    session, ready, authenticated, workspaces, authMode,
    loginDev: (organizationId, userId, displayName) => { setAuthenticated(true); setSession({ mode: "dev", organizationId, userId, displayName: displayName || "Local administrator" }); },
    loginOidc: async () => { window.location.assign(`${API_URL}/api/v1/auth/login`); },
    signupOidc: async details => { sessionStorage.setItem(SIGNUP_KEY, JSON.stringify(details)); window.location.assign(`${API_URL}/api/v1/auth/login`); },
    completeOidc: async () => {
      const initial = await fetchBrowserSession(); const raw = sessionStorage.getItem(SIGNUP_KEY);
      if (raw) {
        const details = JSON.parse(raw) as SignupDetails;
        const response = await fetch(`${API_URL}/api/v1/organizations`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": initial.csrf_token }, body: JSON.stringify({ organization_name: details.organizationName, organization_slug: details.organizationSlug, admin_email: details.adminEmail, admin_display_name: details.adminDisplayName, default_currency: details.defaultCurrency, timezone: details.timezone }) });
        const payload = await response.json().catch(() => ({})) as { organization_id?: string; detail?: { message?: string } };
        if (!response.ok || !payload.organization_id) throw new Error(payload.detail?.message || "Workspace creation failed.");
        sessionStorage.removeItem(SIGNUP_KEY);
        const selection = await fetch(`${API_URL}/api/v1/auth/select-workspace`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": initial.csrf_token }, body: JSON.stringify({ organization_id: payload.organization_id }) });
        if (!selection.ok) throw new Error("Workspace was created but could not be selected.");
      }
      apply(await fetchBrowserSession());
    },
    logout: async () => { if (session?.mode === "oidc") await fetch(`${API_URL}/api/v1/auth/logout`, { method: "POST", credentials: "include", headers: { "X-CSRF-Token": session.csrfToken || "" }, redirect: "manual" }); setSession(null); setAuthenticated(false); setWorkspaces([]); sessionStorage.removeItem(STORAGE_KEY); sessionStorage.removeItem(SIGNUP_KEY); window.location.assign("/login"); },
    selectOrganization: async organizationId => { if (authMode === "dev") { setSession(current => current ? { ...current, organizationId } : current); return; } const csrf = session?.csrfToken || (await fetchBrowserSession()).csrf_token; const response = await fetch(`${API_URL}/api/v1/auth/select-workspace`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify({ organization_id: organizationId }) }); if (!response.ok) throw new Error("That workspace is not available to this identity."); apply(await response.json() as BrowserSession); },
    refreshWorkspaces,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
export function useAuth() { const value = useContext(AuthContext); if (!value) throw new Error("useAuth must be used inside AuthProvider"); return value; }
export function useSession() { const { session } = useAuth(); if (!session) throw new Error("An authenticated session is required."); return session; }
