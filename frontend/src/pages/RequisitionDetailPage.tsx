import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useSession } from "../auth/AuthContext";
import RequisitionEditor, { emptyRequirement, type RequisitionDraft } from "../components/RequisitionEditor";
import { Dialog, ErrorNotice, Field, FormActions, JsonForm, Loading, PageHeader, Status } from "../components/ui";
import { api, post } from "../lib/api";
import type { Budget, ListResponse, Requisition } from "../types";
import type { Policy } from "./ApprovalsPage";

type Req = Omit<Requisition, "lines" | "requirements"> & {
  delivery_location: string | null;
  lines: Array<Requisition["lines"][number] & { category: string | null; specifications: Record<string, unknown>; alternatives_allowed: boolean }>;
  requirements: Array<{ id: string; line_id: string | null; priority: "mandatory" | "preferred"; criterion: string; verification_method: string; source: "human" | "ai_assisted"; confirmed_by_user_id: string | null }>;
};

function editable(req: Req): RequisitionDraft {
  return {
    title: req.title, justification: req.justification, department: req.department || "",
    cost_center: req.cost_center || "", currency: req.currency, need_by_date: req.need_by_date || "",
    delivery_location: req.delivery_location || "",
    lines: req.lines.map(line => ({ key: line.id, description: line.description, quantity: line.quantity, unit: line.unit, estimated_unit_price: line.estimated_unit_price || "", category: line.category || "", alternatives_allowed: line.alternatives_allowed, specifications: line.specifications })),
    requirements: req.requirements.length ? req.requirements.map(item => ({ key: item.id, lineKey: item.line_id || "", priority: item.priority, criterion: item.criterion, verification_method: item.verification_method, source: item.source, confirmed: Boolean(item.confirmed_by_user_id) })) : [emptyRequirement(req.lines[0]?.id)],
  };
}

export default function RequisitionDetailPage() {
  const { id } = useParams(); const session = useSession(); const client = useQueryClient();
  const [dialog, setDialog] = useState<"edit" | "approval" | null>(null); const [error, setError] = useState("");
  const query = useQuery({ queryKey: ["requisition", id], queryFn: () => api<Req>(session, `/api/v1/requisitions/${id}`) });
  const budgets = useQuery({ queryKey: ["budgets"], queryFn: () => api<ListResponse<Budget>>(session, "/api/v1/budgets"), enabled: dialog === "approval" });
  const policies = useQuery({ queryKey: ["approval-policies"], queryFn: () => api<ListResponse<Policy>>(session, "/api/v1/approval-policies"), enabled: dialog === "approval" });
  const change = useMutation({ mutationFn: ({ path, body, method = "POST" }: { path: string; body: unknown; method?: string }) => method === "POST" ? post(session, path, body) : api(session, path, { method, body: JSON.stringify(body) }), onSuccess: () => { setError(""); setDialog(null); void client.invalidateQueries({ queryKey: ["requisition", id] }); void client.invalidateQueries({ queryKey: ["requisitions"] }); void client.invalidateQueries({ queryKey: ["approval-requests"] }); }, onError: reason => setError(reason instanceof Error ? reason.message : "Action failed") });
  if (query.isLoading) return <Loading/>; if (query.error || !query.data) return <ErrorNotice error={query.error}/>;
  const req = query.data;
  const act = (path: string, body: unknown) => change.mutate({ path: `/api/v1/requisitions/${id}${path}`, body });
  return <><Link to="/requisitions" className="back-link">← Requisitions</Link><PageHeader eyebrow="Purchase request" title={req.title} description={req.justification} action={<Status value={req.status}/>}/>{error && <p className="form-error" role="alert">{error}</p>}
    <section className="panel" style={{ padding: 24, marginBottom: 20 }}><h2>Items and requirements</h2><ol>{req.lines.map(line => <li key={line.id}>{line.description} — {line.quantity} {line.unit} at {line.estimated_unit_price || "unpriced"} {req.currency}</li>)}</ol>{req.requirements.map(item => <p key={item.id}><strong>{item.priority}</strong> · {item.criterion} ({item.verification_method})</p>)}</section>
    <section className="panel" style={{ padding: 24 }}><h2>Next action</h2><div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>{["draft", "changes_requested"].includes(req.status) && <><button className="button button-ghost" onClick={() => setDialog("edit")}>Edit items and requirements</button><button className="button button-primary" disabled={change.isPending} onClick={() => act("/submit", { expected_version: req.version })}>Submit request</button></>}{req.status === "submitted" && <button className="button button-primary" onClick={() => setDialog("approval")}>Request budget approval</button>}{req.status === "approved" && <Link className="button button-primary" to="/sourcing">Create RFQ</Link>}{["draft", "submitted"].includes(req.status) && <button className="button button-ghost" disabled={change.isPending} onClick={() => { const reason = window.prompt("Cancellation reason"); if (reason) act("/cancel", { expected_version: req.version, reason }); }}>Cancel request</button>}</div></section>
    <Dialog open={dialog === "approval"} title="Request approval" description="The selected budget reserves funds when all required approvers decide." onClose={() => setDialog(null)}><JsonForm onSubmit={data => change.mutate({ path: `/api/v1/requisitions/${id}/approval-requests`, body: { expected_requisition_version: req.version, budget_id: data.get("budget"), policy_id: data.get("policy") } })}><Field label="Budget"><select name="budget" required><option value="">Select budget</option>{budgets.data?.items.filter(item => item.status === "active" && item.currency === req.currency).map(item => <option key={item.id} value={item.id}>{item.code} — {item.name}</option>)}</select></Field><Field label="Approval policy"><select name="policy" required><option value="">Select policy</option>{policies.data?.items.filter(item => item.status === "active").map(item => <option key={item.id} value={item.id}>{item.name} ({item.required_approvals} approvers)</option>)}</select></Field><FormActions pending={change.isPending} submit="Send for approval" onCancel={() => setDialog(null)}/></JsonForm></Dialog>
    <Dialog open={dialog === "edit"} title="Edit requisition" description="Add or remove items and requirements before submission." onClose={() => setDialog(null)}><RequisitionEditor key={`${req.id}:${req.version}`} initial={editable(req)} pending={change.isPending} onSave={payload => change.mutate({ path: `/api/v1/requisitions/${id}`, method: "PUT", body: { ...payload, expected_version: req.version } })} onCancel={() => setDialog(null)}/></Dialog>
  </>;
}
