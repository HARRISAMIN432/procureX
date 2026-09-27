import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { ErrorNotice, Loading, PageHeader, Status } from "../components/ui";
import { API_URL, ApiError } from "../lib/api";

type Order = { id: string; po_number: string; status: string; version: number; current_revision: number; currency: string; total_amount: string; content_digest: string; lines: Array<{ id: string; description: string; quantity: string; unit: string; unit_price: string }> };

export default function SupplierOrderPage() {
  const { organizationId, purchaseOrderId } = useParams(); const { ready, authenticated, authMode, loginOidc } = useAuth(); const client = useQueryClient(); const [error, setError] = useState("");
  const base = `${API_URL}/api/v1/supplier/orders/${organizationId}/${purchaseOrderId}`;
  const query = useQuery({ queryKey: ["supplier-order", organizationId, purchaseOrderId], enabled: ready && authenticated && authMode === "oidc", queryFn: async () => { const response = await fetch(base, { credentials: "include" }); if (!response.ok) throw new ApiError(response.status, "Order unavailable for this supplier contact"); return response.json() as Promise<Order>; } });
  const change = useMutation({ mutationFn: async (body: unknown) => { const identity = await fetch(`${API_URL}/api/v1/auth/session`, { credentials: "include" }); if (!identity.ok) throw new Error("Sign in again"); const csrf = ((await identity.json()) as { csrf_token: string }).csrf_token; const response = await fetch(`${base}/acknowledge`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify(body) }); if (!response.ok) { const payload = await response.json().catch(() => ({})) as { detail?: string | { message?: string } }; throw new ApiError(response.status, typeof payload.detail === "string" ? payload.detail : payload.detail?.message || "Acknowledgement failed"); } return response.json() as Promise<Order>; }, onSuccess: () => { setError(""); void client.invalidateQueries({ queryKey: ["supplier-order", organizationId, purchaseOrderId] }); }, onError: reason => setError(reason instanceof Error ? reason.message : "Acknowledgement failed") });
  if (!ready) return <main className="center-page"><Loading/></main>;
  if (authMode !== "oidc") return <main className="center-page"><p>Supplier sign-in is unavailable.</p></main>;
  if (!authenticated) return <main className="center-page"><section className="panel" style={{ padding: 32 }}><h1>Supplier purchase order</h1><p>Sign in with your registered supplier contact email.</p><button className="button button-primary" onClick={() => { sessionStorage.setItem("procurex.supplierReturn", window.location.pathname); void loginOidc(); }}>Sign in</button></section></main>;
  if (query.isLoading) return <main className="center-page"><Loading/></main>;
  if (query.error || !query.data) return <main className="center-page"><ErrorNotice error={query.error}/></main>;
  const order = query.data;
  const decide = (acknowledgement: string) => change.mutate({ expected_version: order.version, expected_content_digest: order.content_digest, acknowledgement, note: acknowledgement === "accepted" ? null : window.prompt("Explain your response") || null });
  return <main className="app-main" style={{ maxWidth: 900, margin: "auto", padding: 28 }}><PageHeader eyebrow="Supplier portal" title={order.po_number} description={`Revision ${order.current_revision} · ${order.total_amount} ${order.currency}`} action={<Status value={order.status}/>}/>{error && <p className="form-error" role="alert">{error}</p>}<section className="panel" style={{ padding: 24 }}><h2>Purchase order lines</h2><ol>{order.lines.map(line => <li key={line.id}>{line.description} — {line.quantity} {line.unit} at {line.unit_price} {order.currency}</li>)}</ol>{order.status === "issued" && <div style={{ display: "flex", gap: 8 }}><button className="button button-primary" disabled={change.isPending} onClick={() => decide("accepted")}>Accept order</button><button className="button button-ghost" disabled={change.isPending} onClick={() => decide("rejected")}>Reject order</button><button className="button button-ghost" disabled={change.isPending} onClick={() => decide("changes_proposed")}>Propose changes</button></div>}</section></main>;
}
