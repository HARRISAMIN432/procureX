import { ArrowRight, Fingerprint, LockKeyhole, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

export default function LoginPage() {
  const { session, authMode, loginDev, loginOidc } = useAuth();
  const [error, setError] = useState("");
  if (session) return <Navigate to="/" replace/>;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setError(""); const data = new FormData(event.currentTarget);
    const org = String(data.get("organizationId") || "").trim();
    try { if (authMode === "dev") loginDev(org, String(data.get("userId") || "").trim(), String(data.get("displayName") || "")); else await loginOidc(org); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Sign-in failed."); }
  };
  return <main className="auth-page"><section className="auth-panel"><div className="auth-brand"><div className="brand-mark">PX</div><strong>ProcureX</strong></div><div className="auth-copy"><p className="eyebrow">Procurement control workspace</p><h1>Decisions you can trace.<br/>Purchasing you can trust.</h1><p>Bring requests, supplier evidence, approvals, awards and delivery into one controlled record.</p></div><div className="auth-assurance"><div><ShieldCheck/><span><strong>Evidence-bound</strong><small>Every decision links to its source</small></span></div><div><Fingerprint/><span><strong>Tenant isolated</strong><small>Access follows organization membership</small></span></div><div><LockKeyhole/><span><strong>Human authorized</strong><small>AI never approves or purchases</small></span></div></div></section><section className="login-panel"><form onSubmit={(event) => void submit(event)}><div><p className="eyebrow">Secure access</p><h2>Open your workspace</h2><p>Enter the workspace ID from your invitation.</p></div><label className="field"><span>Workspace ID</span><input name="organizationId" required placeholder="00000000-0000-0000-0000-000000000000" autoComplete="organization"/></label>{authMode === "dev" && <><label className="field"><span>Local user ID</span><input name="userId" required placeholder="Development user UUID"/></label><label className="field"><span>Display name</span><input name="displayName" defaultValue="Local administrator"/></label></>}{error && <p className="form-error">{error}</p>}<button className="button button-primary button-wide">{authMode === "dev" ? "Continue locally" : "Continue with identity provider"}<ArrowRight size={17}/></button><p className="security-note">Your workspace selection is always verified by the API. Entering an ID never grants access by itself.</p></form></section></main>;
}
