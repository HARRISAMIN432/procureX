import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { UserManager, WebStorageStateStore, type User } from "oidc-client-ts";
import type { Session, Workspace } from "../types";
import { API_URL } from "../lib/api";

const STORAGE_KEY = "procurex.session";
const ORGANIZATION_KEY = "procurex.organization";
const SIGNUP_KEY = "procurex.signup";
const authMode = (import.meta.env.VITE_AUTH_MODE || "dev") as "dev" | "oidc";
const authority = import.meta.env.VITE_OIDC_AUTHORITY as string | undefined;
const clientId = import.meta.env.VITE_OIDC_CLIENT_ID as string | undefined;

const manager = authMode === "oidc" && authority && clientId ? new UserManager({
  authority,
  client_id: clientId,
  redirect_uri: `${window.location.origin}/auth/callback`,
  post_logout_redirect_uri: `${window.location.origin}/login`,
  response_type: "code",
  scope: import.meta.env.VITE_OIDC_SCOPE || "openid profile email",
  automaticSilentRenew: true,
  monitorSession: true,
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
}) : null;

type AuthValue = {
  session: Session | null;
  ready: boolean;
  authenticated: boolean;
  workspaces: Workspace[];
  authMode: "dev" | "oidc";
  loginDev: (organizationId: string, userId: string, displayName: string) => void;
  loginOidc: () => Promise<void>;
  signupOidc: (details: SignupDetails) => Promise<void>;
  completeOidc: () => Promise<void>;
  logout: () => Promise<void>;
  selectOrganization: (id: string) => Promise<void>;
  refreshWorkspaces: () => Promise<void>;
};

export type SignupDetails = { organizationName: string; organizationSlug: string; adminEmail: string; adminDisplayName: string; defaultCurrency: string; timezone: string };

const AuthContext = createContext<AuthValue | null>(null);

const fromUser = (user: User, organizationId: string): Session => ({
  mode: "oidc", organizationId, accessToken: user.access_token,
  displayName: String(user.profile.name || user.profile.email || "ProcureX user"),
});

async function fetchWorkspaces(user: User): Promise<Workspace[]> {
  const response = await fetch(`${API_URL}/api/v1/organizations/mine`, {
    headers: { Authorization: `Bearer ${user.access_token}`, Accept: "application/json" },
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: string | { message?: string } };
    const message = typeof payload.detail === "string" ? payload.detail : payload.detail?.message;
    throw new Error(message || "Your workspaces could not be loaded.");
  }
  return response.json() as Promise<Workspace[]>;
}

function storedSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) as Session : null;
  } catch {
    sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => authMode === "dev" ? storedSession() : null);
  const [ready, setReady] = useState(authMode === "dev");
  const [authenticated, setAuthenticated] = useState(authMode === "dev" && Boolean(session));
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);

  const applyUser = async (user: User) => {
    const available = await fetchWorkspaces(user);
    setAuthenticated(true);
    setWorkspaces(available);
    const selected = sessionStorage.getItem(ORGANIZATION_KEY);
    const organizationId = available.some((workspace) => workspace.organization_id === selected)
      ? selected
      : available.length === 1 ? available[0].organization_id : null;
    if (organizationId) {
      sessionStorage.setItem(ORGANIZATION_KEY, organizationId);
      setSession(fromUser(user, organizationId));
    } else {
      setSession(null);
    }
  };

  useEffect(() => {
    if (!manager) return;
    const userLoaded = (user: User) => { void applyUser(user).catch(() => setSession(null)); };
    const userEnded = () => {
      setSession(null);
      setAuthenticated(false);
      setWorkspaces([]);
      sessionStorage.removeItem(ORGANIZATION_KEY);
    };
    manager.events.addUserLoaded(userLoaded);
    manager.events.addUserUnloaded(userEnded);
    manager.events.addAccessTokenExpired(userEnded);
    manager.getUser()
      .then(async (user) => {
        if (user && !user.expired) await applyUser(user);
        else userEnded();
      })
      .catch(userEnded)
      .finally(() => setReady(true));
    return () => {
      manager.events.removeUserLoaded(userLoaded);
      manager.events.removeUserUnloaded(userEnded);
      manager.events.removeAccessTokenExpired(userEnded);
    };
  }, []);

  useEffect(() => {
    if (session) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    else sessionStorage.removeItem(STORAGE_KEY);
  }, [session]);

  const refreshWorkspaces = async () => {
    if (!manager) return;
    const user = await manager.getUser();
    if (!user || user.expired) throw new Error("Your sign-in session has expired.");
    await applyUser(user);
  };

  const value: AuthValue = {
    session, ready, authenticated, workspaces, authMode,
    loginDev: (organizationId, userId, displayName) => {
      setAuthenticated(true);
      setSession({ mode: "dev", organizationId, userId, displayName: displayName || "Local administrator" });
    },
    loginOidc: async () => {
      if (!manager) throw new Error("OIDC is not configured.");
      await manager.signinRedirect({ state: { intent: "signin" } });
    },
    signupOidc: async (details) => {
      if (!manager) throw new Error("OIDC is not configured.");
      sessionStorage.setItem(SIGNUP_KEY, JSON.stringify(details));
      await manager.signinRedirect({ state: { signup: true } });
    },
    completeOidc: async () => {
      if (!manager) throw new Error("OIDC is not configured.");
      const user = await manager.signinRedirectCallback();
      const state = user.state as { signup?: boolean } | undefined;
      if (state?.signup) {
        const raw = sessionStorage.getItem(SIGNUP_KEY);
        if (!raw) throw new Error("Signup details expired. Please start again.");
        const details = JSON.parse(raw) as SignupDetails;
        const response = await fetch(`${API_URL}/api/v1/organizations`, {
          method: "POST",
          headers: { Authorization: `Bearer ${user.access_token}`, "Content-Type": "application/json" },
          body: JSON.stringify({ organization_name: details.organizationName, organization_slug: details.organizationSlug, admin_email: details.adminEmail, admin_display_name: details.adminDisplayName, default_currency: details.defaultCurrency, timezone: details.timezone }),
        });
        const payload = await response.json() as { organization_id?: string; detail?: { message?: string } };
        if (!response.ok || !payload.organization_id) throw new Error(payload.detail?.message || "Workspace creation failed.");
        sessionStorage.removeItem(SIGNUP_KEY);
        sessionStorage.setItem(ORGANIZATION_KEY, payload.organization_id);
      }
      await applyUser(user);
    },
    logout: async () => {
      setSession(null);
      setAuthenticated(false);
      setWorkspaces([]);
      sessionStorage.removeItem(ORGANIZATION_KEY);
      sessionStorage.removeItem(SIGNUP_KEY);
      if (manager) await manager.signoutRedirect();
    },
    selectOrganization: async (organizationId) => {
      if (authMode === "dev") {
        setSession((current) => current ? { ...current, organizationId } : current);
        return;
      }
      if (!workspaces.some((workspace) => workspace.organization_id === organizationId)) {
        throw new Error("That workspace is not available to this identity.");
      }
      const user = await manager?.getUser();
      if (!user || user.expired) throw new Error("Your sign-in session has expired.");
      sessionStorage.setItem(ORGANIZATION_KEY, organizationId);
      setSession(fromUser(user, organizationId));
    },
    refreshWorkspaces,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export function useSession() {
  const { session } = useAuth();
  if (!session) throw new Error("An authenticated session is required.");
  return session;
}
