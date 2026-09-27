import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useSession } from "../auth/AuthContext";
import RequisitionEditor, { emptyLine, emptyRequirement, type RequisitionDraft } from "../components/RequisitionEditor";
import { Dialog, EmptyState, ErrorNotice, Loading, PageHeader, Status } from "../components/ui";
import { post, api } from "../lib/api";
import { money, relativeDate } from "../lib/format";
import type { ListResponse, Requisition } from "../types";

const newDraft = (): RequisitionDraft => {
  const line = emptyLine();
  return { title: "", justification: "", department: "", cost_center: "", currency: "PKR", need_by_date: "", delivery_location: "", lines: [line], requirements: [emptyRequirement(line.key)] };
};

export default function RequisitionsPage() {
  const session = useSession(); const client = useQueryClient(); const [params, setParams] = useSearchParams();
  const [open, setOpen] = useState(params.get("new") === "1"); const [draft, setDraft] = useState(newDraft);
  useEffect(() => { if (params.get("new") === "1") setOpen(true); }, [params]);
  const query = useQuery({ queryKey: ["requisitions", session.organizationId], queryFn: () => api<ListResponse<Requisition>>(session, "/api/v1/requisitions?limit=100") });
  const create = useMutation({ mutationFn: (body: Record<string, unknown>) => post(session, "/api/v1/requisitions", body), onSuccess: () => { void client.invalidateQueries({ queryKey: ["requisitions"] }); close(); } });
  const close = () => { setOpen(false); setParams({}); setDraft(newDraft()); };
  return <><PageHeader eyebrow="Demand" title="Requisitions" description="Shape purchase needs before they consume budget or enter the market." action={<button className="button button-primary" onClick={() => setOpen(true)}><Plus size={16}/>New requisition</button>}/>
    {query.isLoading ? <Loading/> : query.error ? <ErrorNotice error={query.error}/> : !query.data?.items.length ? <EmptyState title="No requisitions yet" detail="Create the first request to begin a controlled purchase." action={<button className="button button-primary" onClick={() => setOpen(true)}>Create requisition</button>}/> : <section className="data-table-wrap"><table className="data-table"><thead><tr><th>Request</th><th>Department</th><th>Estimate</th><th>Need by</th><th>Status</th><th>Updated</th></tr></thead><tbody>{query.data.items.map(item => <tr key={item.id}><td><Link to={`/requisitions/${item.id}`}><strong>{item.title}</strong><span>REQ · v{item.version} · {item.lines.length} lines</span></Link></td><td>{item.department || "—"}</td><td>{money(item.lines.reduce((sum, line) => sum + Number(line.quantity) * Number(line.estimated_unit_price || 0), 0), item.currency)}</td><td>{item.need_by_date || "Not set"}</td><td><Status value={item.status}/></td><td>{relativeDate(item.updated_at)}</td></tr>)}</tbody></table></section>}
    <Dialog open={open} onClose={close} title="New requisition" description="Add every item and testable requirement before submission."><RequisitionEditor key={draft.lines[0].key} initial={draft} pending={create.isPending} onSave={payload => create.mutate(payload)} onCancel={close}/>{create.error && <p className="form-error" role="alert">{create.error.message}</p>}</Dialog>
  </>;
}
