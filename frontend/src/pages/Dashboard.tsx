import { useQueries } from "@tanstack/react-query";
import { ArrowRight, Banknote, CheckCircle2, ClipboardList, Clock3, FileWarning, Plus, Store } from "lucide-react";
import { Link } from "react-router-dom";
import { useSession } from "../auth/AuthContext";
import { ErrorNotice, Loading, PageHeader, Status } from "../components/ui";
import { api } from "../lib/api";
import { money, relativeDate, shortDate } from "../lib/format";
import type { Budget, ListResponse, Requisition, Rfq, Supplier } from "../types";

export default function Dashboard() {
  const session = useSession();
  const results = useQueries({ queries: [
    { queryKey: ["requisitions"], queryFn: () => api<ListResponse<Requisition>>(session, "/api/v1/requisitions?limit=50") },
    { queryKey: ["suppliers"], queryFn: () => api<ListResponse<Supplier>>(session, "/api/v1/suppliers?limit=50") },
    { queryKey: ["rfqs"], queryFn: () => api<ListResponse<Rfq>>(session, "/api/v1/rfqs?limit=50") },
    { queryKey: ["budgets"], queryFn: () => api<ListResponse<Budget>>(session, "/api/v1/budgets?limit=50") },
  ]});
  if (results.some((item) => item.isLoading)) return <Loading/>;
  const failed = results.find((item) => item.error); if (failed) return <ErrorNotice error={failed.error}/>;
  const reqs = (results[0].data as ListResponse<Requisition>).items; const suppliers = (results[1].data as ListResponse<Supplier>).items; const rfqs = (results[2].data as ListResponse<Rfq>).items; const budgets = (results[3].data as ListResponse<Budget>).items;
  const pending = reqs.filter((item) => ["draft", "submitted"].includes(item.status)); const openRfqs = rfqs.filter((item) => ["published", "draft"].includes(item.status));
  const available = budgets.reduce((sum, item) => sum + Number(item.available), 0);
  const today = new Intl.DateTimeFormat("en-PK", { weekday: "long", day: "numeric", month: "long" }).format(new Date());
  return <><PageHeader eyebrow={today} title="Procurement overview" description="Work requiring attention across your organization." action={<Link to="/requisitions?new=1" className="button button-primary"><Plus size={16}/>New requisition</Link>}/>
    <section className="metric-grid"><article><span><ClipboardList/>Open requests</span><strong>{pending.length}</strong><small>{reqs.filter((item) => item.status === "submitted").length} awaiting approval</small></article><article><span><Clock3/>Active sourcing</span><strong>{openRfqs.length}</strong><small>{rfqs.reduce((n, item) => n + item.submissions.length, 0)} supplier submissions</small></article><article><span><Store/>Qualified suppliers</span><strong>{suppliers.filter((item) => item.status === "approved").length}</strong><small>{suppliers.filter((item) => item.status === "pending_review").length} pending review</small></article><article><span><Banknote/>Available budget</span><strong>{money(available)}</strong><small>Across {budgets.length} active budgets</small></article></section>
    <div className="dashboard-grid"><section className="panel span-2"><header className="panel-header"><div><p className="eyebrow">Work queue</p><h2>Requests needing action</h2></div><Link to="/requisitions">View all <ArrowRight size={15}/></Link></header>{pending.length ? <div className="record-list">{pending.slice(0, 6).map((item) => <Link className="record-row" to={`/requisitions/${item.id}`} key={item.id}><div className="record-icon"><ClipboardList size={17}/></div><div className="record-main"><strong>{item.title}</strong><span>{item.department || "No department"} · {item.lines.length} line{item.lines.length === 1 ? "" : "s"}</span></div><div className="record-meta"><Status value={item.status}/><span>Updated {relativeDate(item.updated_at)}</span></div></Link>)}</div> : <div className="compact-empty"><CheckCircle2/><span><strong>Queue clear</strong><small>No requests need action.</small></span></div>}</section>
      <section className="panel"><header className="panel-header"><div><p className="eyebrow">Deadlines</p><h2>Open sourcing</h2></div></header><div className="deadline-list">{openRfqs.slice(0, 5).map((item) => <Link to={`/sourcing/${item.id}`} key={item.id}><div><strong>{item.title}</strong><span>{item.submissions.length}/{item.invitations.length} responses</span></div><time>{shortDate(item.submission_deadline)}</time></Link>)}{!openRfqs.length && <div className="compact-empty"><FileWarning/><span><strong>No active RFQs</strong><small>Published events appear here.</small></span></div>}</div></section></div></>;
}
