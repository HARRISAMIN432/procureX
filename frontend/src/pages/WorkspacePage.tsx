import { ArrowRight, Building2, LogOut, RefreshCw, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { Loading, Status } from "../components/ui";

export default function WorkspacePage() {
  const { ready, authenticated, workspaces, selectOrganization, refreshWorkspaces, logout, authMode } = useAuth();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const navigate = useNavigate();
  if (!ready) return <main className="center-page"><Loading/></main>;
  if (authMode !== "oidc" || !authenticated) return <Navigate to="/login" replace/>;

  const select = async (organizationId: string) => {
    setError(""); setBusy(organizationId);
    try { await selectOrganization(organizationId); navigate("/"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Workspace access failed."); }
    finally { setBusy(null); }
  };

  const refresh = async () => {
    setError(""); setBusy("refresh");
    try { await refreshWorkspaces(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Workspaces could not be refreshed."); }
    finally { setBusy(null); }
  };

  return <main className="workspace-page"><section className="workspace-card"><header><div className="brand-mark">PX</div><div><p className="eyebrow">Secure organization access</p><h1>Choose a workspace</h1><p>Only active memberships and verified invitations are shown.</p></div></header>{error && <p className="form-error">{error}</p>}{workspaces.length ? <div className="workspace-list">{workspaces.map((workspace) => <button key={workspace.membership_id} onClick={() => void select(workspace.organization_id)} disabled={busy !== null}><span className="workspace-icon"><Building2 size={20}/></span><span><strong>{workspace.organization_name}</strong><small>{workspace.organization_slug}</small></span><Status value={workspace.is_pending_invitation ? "invited" : workspace.membership_status}/><ArrowRight size={18}/></button>)}</div> : <div className="workspace-empty"><ShieldCheck/><h2>No workspace access yet</h2><p>Ask an administrator to invite your verified email, then refresh this page.</p></div>}<footer><button className="button button-secondary" onClick={() => void refresh()} disabled={busy !== null}><RefreshCw size={15}/>Refresh access</button><button className="button button-ghost" onClick={() => void logout()}><LogOut size={15}/>Sign out</button></footer></section></main>;
}
