import { ArrowRight, Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useSession } from "../auth/AuthContext";
import { ErrorNotice, Loading, PageHeader, Status } from "../components/ui";
import { api } from "../lib/api";

const copy = {
  evaluations: ["Evaluation workspace", "Evaluations", "Open a known evaluation to inspect requirement outcomes, landed costs, scores and grounded analysis."],
  awards: ["Decision governance", "Awards", "Open an award dossier to inspect its immutable recommendation, allocation and approval decisions."],
  operations: ["Purchase operations", "Orders and invoices", "Issue orders, receive goods and match supplier invoices."],
} as const;
export default function LookupPage({ kind }: { kind: keyof typeof copy }) { const [type, setType] = useState(kind === "operations" ? "purchase-order" : kind.slice(0, -1)); const navigate = useNavigate(); const session = useSession(); const [eyebrow, title, description] = copy[kind]; const path = type === "purchase-order" ? "purchase-orders" : `${type}s`; const records = useQuery({ queryKey: ["lookup", session.organizationId, path], queryFn: () => api<Array<{ id: string; status: string; rfq_id?: string; po_number?: string; supplier_invoice_number?: string; content_digest?: string }>>(session, `/api/v1/${path}`) }); const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const id = String(new FormData(event.currentTarget).get("id")); navigate(`/record/${type}/${id}`); };
  return <><PageHeader eyebrow={eyebrow} title={title} description={description}/>{kind === "operations" && <div className="form-actions"><button className="button button-ghost" onClick={() => setType("purchase-order")}>Orders</button><button className="button button-ghost" onClick={() => setType("invoice")}>Invoices</button></div>}{records.isLoading ? <Loading/> : records.error ? <ErrorNotice error={records.error}/> : <section className="panel" style={{ padding: 24 }}><h2>Recent records</h2>{records.data?.length ? records.data.map(item => <p key={item.id}><Link to={`/record/${type}/${item.id}`}>{item.po_number || item.supplier_invoice_number || `${type} ${item.id.slice(0, 8)}`}</Link> · <Status value={item.status}/></p>) : <p>No {type} records yet. Complete the preceding workflow step to create one.</p>}</section>}<section className="lookup-panel"><div className="lookup-mark"><Search size={25}/></div><div><h2>Open a record by ID</h2><p>Use the identifier from a notification or audit trail.</p></div><form onSubmit={submit}>{kind === "operations" && <select value={type} onChange={(event) => setType(event.target.value)} aria-label="Record type"><option value="purchase-order">Purchase order</option><option value="invoice">Invoice</option></select>}<input name="id" required placeholder="Record UUID" aria-label="Record ID"/><button className="button button-primary">Open record<ArrowRight size={16}/></button></form></section></>;
}
