import { useState, type FormEvent } from "react";
import { Field } from "./ui";

export type EditableLine = {
  key: string; description: string; quantity: string; unit: string;
  estimated_unit_price: string; category: string; alternatives_allowed: boolean;
  specifications: Record<string, unknown>;
};
export type EditableRequirement = {
  key: string; lineKey: string; priority: "mandatory" | "preferred";
  criterion: string; verification_method: string;
  source: "human" | "ai_assisted"; confirmed: boolean;
};
export type RequisitionDraft = {
  title: string; justification: string; department: string; cost_center: string;
  currency: string; need_by_date: string; delivery_location: string;
  lines: EditableLine[]; requirements: EditableRequirement[];
};

export const emptyLine = (): EditableLine => ({ key: crypto.randomUUID(), description: "", quantity: "1", unit: "each", estimated_unit_price: "", category: "", alternatives_allowed: false, specifications: {} });
export const emptyRequirement = (lineKey = ""): EditableRequirement => ({ key: crypto.randomUUID(), lineKey, priority: "mandatory", criterion: "", verification_method: "Review supplier quotation", source: "human", confirmed: true });

export default function RequisitionEditor({ initial, pending, onSave, onCancel }: { initial: RequisitionDraft; pending: boolean; onSave: (payload: Record<string, unknown>) => void; onCancel: () => void }) {
  const [draft, setDraft] = useState(initial);
  const [error, setError] = useState("");
  const setField = (name: keyof Omit<RequisitionDraft, "lines" | "requirements">, value: string) => setDraft(current => ({ ...current, [name]: value }));
  const setLine = (key: string, patch: Partial<EditableLine>) => setDraft(current => ({ ...current, lines: current.lines.map(item => item.key === key ? { ...item, ...patch } : item) }));
  const setRequirement = (key: string, patch: Partial<EditableRequirement>) => setDraft(current => ({ ...current, requirements: current.requirements.map(item => item.key === key ? { ...item, ...patch } : item) }));
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!draft.lines.length || !draft.requirements.length) { setError("Add at least one item and one testable requirement."); return; }
    if (draft.requirements.some(item => item.lineKey && !draft.lines.some(line => line.key === item.lineKey))) { setError("A requirement points to a removed item."); return; }
    setError("");
    onSave({
      title: draft.title, justification: draft.justification,
      department: draft.department || null, cost_center: draft.cost_center || null,
      currency: draft.currency, need_by_date: draft.need_by_date || null,
      delivery_location: draft.delivery_location || null,
      lines: draft.lines.map((line, index) => ({ line_number: index + 1, description: line.description, quantity: line.quantity, unit: line.unit, estimated_unit_price: line.estimated_unit_price || null, category: line.category || null, alternatives_allowed: line.alternatives_allowed, specifications: line.specifications })),
      requirements: draft.requirements.map(item => ({ line_number: item.lineKey ? draft.lines.findIndex(line => line.key === item.lineKey) + 1 : null, priority: item.priority, criterion: item.criterion, verification_method: item.verification_method, source: item.source, confirmed: item.confirmed })),
    });
  };
  return <form className="form" onSubmit={submit}>
    <div className="form-grid"><Field label="Title"><input required minLength={2} value={draft.title} onChange={event => setField("title", event.target.value)}/></Field><Field label="Justification"><textarea required minLength={2} value={draft.justification} onChange={event => setField("justification", event.target.value)}/></Field><Field label="Department"><input value={draft.department} onChange={event => setField("department", event.target.value)}/></Field><Field label="Cost center"><input value={draft.cost_center} onChange={event => setField("cost_center", event.target.value)}/></Field><Field label="Currency"><input required pattern="[A-Z]{3}" maxLength={3} value={draft.currency} onChange={event => setField("currency", event.target.value.toUpperCase())}/></Field><Field label="Need-by date"><input type="date" value={draft.need_by_date} onChange={event => setField("need_by_date", event.target.value)}/></Field><Field label="Delivery location"><input value={draft.delivery_location} onChange={event => setField("delivery_location", event.target.value)}/></Field></div>
    <h3>Items</h3>{draft.lines.map((line, index) => <section className="panel" key={line.key} style={{ padding: 16, marginBottom: 12 }}><h4>Item {index + 1}</h4><div className="form-grid"><Field label="Description"><input required value={line.description} onChange={event => setLine(line.key, { description: event.target.value })}/></Field><Field label="Quantity"><input required type="number" min="0.0001" step="any" value={line.quantity} onChange={event => setLine(line.key, { quantity: event.target.value })}/></Field><Field label="Unit"><input required value={line.unit} onChange={event => setLine(line.key, { unit: event.target.value })}/></Field><Field label="Estimated unit price"><input type="number" min="0" step="any" value={line.estimated_unit_price} onChange={event => setLine(line.key, { estimated_unit_price: event.target.value })}/></Field><Field label="Category"><input value={line.category} onChange={event => setLine(line.key, { category: event.target.value })}/></Field><label className="check-field"><input type="checkbox" checked={line.alternatives_allowed} onChange={event => setLine(line.key, { alternatives_allowed: event.target.checked })}/>Allow alternatives</label></div><button type="button" className="button button-ghost" disabled={draft.lines.length === 1} onClick={() => setDraft(current => ({ ...current, lines: current.lines.filter(item => item.key !== line.key), requirements: current.requirements.filter(item => item.lineKey !== line.key) }))}>Remove item</button></section>)}<button type="button" className="button button-ghost" onClick={() => setDraft(current => ({ ...current, lines: [...current.lines, emptyLine()] }))}>Add item</button>
    <h3>Requirements</h3>{draft.requirements.map(item => <section className="panel" key={item.key} style={{ padding: 16, marginBottom: 12 }}><div className="form-grid"><Field label="Applies to"><select value={item.lineKey} onChange={event => setRequirement(item.key, { lineKey: event.target.value })}><option value="">Entire requisition</option>{draft.lines.map((line, index) => <option value={line.key} key={line.key}>Item {index + 1}: {line.description || "Untitled"}</option>)}</select></Field><Field label="Priority"><select value={item.priority} onChange={event => setRequirement(item.key, { priority: event.target.value as EditableRequirement["priority"] })}><option value="mandatory">Mandatory</option><option value="preferred">Preferred</option></select></Field><Field label="Criterion"><textarea required value={item.criterion} onChange={event => setRequirement(item.key, { criterion: event.target.value })}/></Field><Field label="Verification method"><input required value={item.verification_method} onChange={event => setRequirement(item.key, { verification_method: event.target.value })}/></Field></div>{item.source === "ai_assisted" && <label className="check-field"><input type="checkbox" checked={item.confirmed} onChange={event => setRequirement(item.key, { confirmed: event.target.checked })}/>I reviewed and confirm this AI-assisted requirement</label>}<button type="button" className="button button-ghost" disabled={draft.requirements.length === 1} onClick={() => setDraft(current => ({ ...current, requirements: current.requirements.filter(candidate => candidate.key !== item.key) }))}>Remove requirement</button></section>)}<button type="button" className="button button-ghost" onClick={() => setDraft(current => ({ ...current, requirements: [...current.requirements, emptyRequirement()] }))}>Add requirement</button>
    {error && <p className="form-error" role="alert">{error}</p>}<div className="form-actions"><button type="button" className="button button-ghost" onClick={onCancel}>Cancel</button><button className="button button-primary" disabled={pending}>{pending ? "Saving…" : "Save requisition"}</button></div>
  </form>;
}
