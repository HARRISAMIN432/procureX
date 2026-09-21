import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { UserManager, WebStorageStateStore, type User } from "oidc-client-ts";
import type { Session } from "../types";

const STORAGE_KEY = "procurex.session";
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
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
}) : null;

type AuthValue = {
  session: Session | null; ready: boolean; authMode: "dev" | "oidc";
  loginDev: (organizationId: string, userId: string, displayName: string) => void;
  loginOidc: (organizationId: string) => Promise<void>;
  completeOidc: () => Promise<void>;
  logout: () => Promise<void>;
  setOrganization: (id: string) => void;
};

const AuthContext = createContext<AuthValue | null>(null);

const fromUser = (user: User, organizationId: string): Session => ({
  mode: "oidc", organizationId, accessToken: user.access_token,
  displayName: String(user.profile.name || user.profile.email || "ProcureX user"),
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) as Session : null;
  });
  const [ready, setReady] = useState(authMode === "dev");

  useEffect(() => {
    if (!manager) return;
    manager.getUser().then((user) => {
      if (user && !user.expired) {
        const stored = sessionStorage.getItem(STORAGE_KEY);
        const org = sessionStorage.getItem("procurex.organization") || (stored ? (JSON.parse(stored) as Session).organizationId : "");
        if (org) setSession(fromUser(user, org));
      }
      setReady(true);
    });
  }, []);

  useEffect(() => {
    if (session) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session));
    else sessionStorage.removeItem(STORAGE_KEY);
  }, [session]);

  const value = useMemo<AuthValue>(() => ({
    session, ready, authMode,
    loginDev: (organizationId, userId, displayName) => setSession({ mode: "dev", organizationId, userId, displayName: displayName || "Local administrator" }),
    loginOidc: async (organizationId) => {
      if (!manager) throw new Error("OIDC is not configured.");
      sessionStorage.setItem("procurex.organization", organizationId);
      await manager.signinRedirect({ state: { organizationId } });
    },
    completeOidc: async () => {
      if (!manager) throw new Error("OIDC is not configured.");
      const user = await manager.signinRedirectCallback();
      const state = user.state as { organizationId?: string } | undefined;
      const organizationId = state?.organizationId || sessionStorage.getItem("procurex.organization") || "";
      setSession(fromUser(user, organizationId));
    },
    logout: async () => {
      setSession(null);
      if (manager) await manager.signoutRedirect();
    },
    setOrganization: (organizationId) => setSession((current) => current ? { ...current, organizationId } : current),
  }), [session, ready]);

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
