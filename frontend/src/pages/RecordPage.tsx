import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { useSession } from "../auth/AuthContext";
import { ErrorNotice, Loading, PageHeader, Status } from "../components/ui";
import { api } from "../lib/api";
import { humanize } from "../lib/format";

const paths: Record<string, string> = {
  requisition: "/api/v1/requisitions/", rfq: "/api/v1/rfqs/",
  evaluation: "/api/v1/evaluations/", award: "/api/v1/awards/",
  "purchase-order": "/api/v1/purchase-orders/", invoice: "/api/v1/invoices/",
};

export default function RecordPage() {
  const { type = "", id = "" } = useParams();
  const session = useSession();
  const query = useQuery({
    queryKey: ["record", type, id],
    queryFn: () => api<Record<string, unknown>>(session, `${paths[type]}${id}`),
    enabled: Boolean(paths[type] && id),
  });
  if (query.isLoading) return <Loading/>;
  if (query.error) return <ErrorNotice error={query.error}/>;
  const record = query.data!;
  const title = String(record.title || record.po_number || record.invoice_number || `${humanize(type)} record`);
  const status = String(record.status || "recorded");
  return <><Link to=".." className="back-link"><ArrowLeft size={15}/>Back</Link><PageHeader eyebrow={humanize(type)} title={title} action={<Status value={status}/>}/><div className="detail-grid"><section className="panel span-2"><header className="panel-header"><h2>Record detail</h2><span className="mono-label">{id}</span></header><dl className="detail-list">{Object.entries(record).filter(([key, value]) => !Array.isArray(value) && typeof value !== "object" && !["id", "organization_id", "title", "status"].includes(key)).slice(0, 18).map(([key, value]) => <div key={key}><dt>{humanize(key)}</dt><dd>{String(value ?? "—")}</dd></div>)}</dl></section><section className="panel"><header className="panel-header"><h2>Evidence</h2></header><p className="panel-copy">This record is rendered directly from the tenant-authorized API response. Related immutable versions, decisions and evidence remain authoritative in the backend.</p></section></div></>;
}
