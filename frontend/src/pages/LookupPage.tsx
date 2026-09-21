import { ArrowRight, Search } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components/ui";

const copy = {
  evaluations: ["Evaluation workspace", "Evaluations", "Open a known evaluation to inspect requirement outcomes, landed costs, scores and grounded analysis."],
  awards: ["Decision governance", "Awards", "Open an award dossier to inspect its immutable recommendation, allocation and approval decisions."],
  operations: ["Purchase operations", "Orders and invoices", "Open a purchase order or invoice by ID. The API currently exposes detail records rather than organization-wide listings."],
} as const;
export default function LookupPage({ kind }: { kind: keyof typeof copy }) { const [type, setType] = useState(kind === "operations" ? "purchase-order" : kind.slice(0, -1)); const navigate = useNavigate(); const [eyebrow, title, description] = copy[kind]; const submit = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); const id = String(new FormData(event.currentTarget).get("id")); navigate(`/record/${type}/${id}`); };
  return <><PageHeader eyebrow={eyebrow} title={title} description={description}/><section className="lookup-panel"><div className="lookup-mark"><Search size={25}/></div><div><h2>Open a controlled record</h2><p>Paste the identifier from an approval notification, audit trail or related record.</p></div><form onSubmit={submit}>{kind === "operations" && <select value={type} onChange={(event) => setType(event.target.value)} aria-label="Record type"><option value="purchase-order">Purchase order</option><option value="invoice">Invoice</option></select>}<input name="id" required placeholder="Record UUID" aria-label="Record ID"/><button className="button button-primary">Open record<ArrowRight size={16}/></button></form></section></>;
}
