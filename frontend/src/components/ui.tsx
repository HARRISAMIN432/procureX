import { AlertTriangle, Check, LoaderCircle, Search, X } from "lucide-react";
import { useEffect, type FormEvent, type ReactNode } from "react";
import { humanize } from "../lib/format";

export function Status({ value }: { value: string }) {
  const tone = ["approved", "active", "completed", "clean", "parsed", "reviewed", "issued", "matched", "qualified"].includes(value) ? "good"
    : ["rejected", "failed", "infected", "cancelled", "suspended", "revoked", "ineligible"].includes(value) ? "bad"
    : ["pending", "submitted", "running", "parsing", "scanning", "queued", "awaiting_review"].includes(value) ? "warn" : "neutral";
  return <span className={`status status-${tone}`}><span aria-hidden="true" />{humanize(value)}</span>;
}

export function PageHeader({ eyebrow, title, description, action }: { eyebrow?: string; title: string; description?: string; action?: ReactNode }) {
  return <header className="page-header"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>{description && <p className="page-description">{description}</p>}</div>{action && <div className="header-action">{action}</div>}</header>;
}

export function EmptyState({ title, detail, action }: { title: string; detail: string; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-mark"><Search size={22}/></div><h3>{title}</h3><p>{detail}</p>{action}</div>;
}

export function Loading() { return <div className="loading" role="status"><LoaderCircle className="spin" size={18}/> Loading workspace data…</div>; }

export function ErrorNotice({ error }: { error: unknown }) {
  return <div className="error-notice" role="alert"><AlertTriangle size={18}/><div><strong>Couldn’t load this view</strong><p>{error instanceof Error ? error.message : "Try again in a moment."}</p></div></div>;
}

export function Dialog({ open, title, description, children, onClose }: { open: boolean; title: string; description?: string; children: ReactNode; onClose: () => void }) {
  useEffect(() => { const close = (event: KeyboardEvent) => event.key === "Escape" && onClose(); document.addEventListener("keydown", close); return () => document.removeEventListener("keydown", close); }, [onClose]);
  if (!open) return null;
  return <div className="dialog-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}><section className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><header><div><h2 id="dialog-title">{title}</h2>{description && <p>{description}</p>}</div><button className="icon-button" onClick={onClose} aria-label="Close"><X size={19}/></button></header>{children}</section></div>;
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) { return <label className="field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>; }

export function FormActions({ pending, submit = "Save", onCancel }: { pending?: boolean; submit?: string; onCancel: () => void }) {
  return <div className="form-actions"><button type="button" className="button button-ghost" onClick={onCancel}>Cancel</button><button className="button button-primary" disabled={pending}>{pending ? <LoaderCircle className="spin" size={16}/> : <Check size={16}/>} {submit}</button></div>;
}

export function JsonForm({ onSubmit, children }: { onSubmit: (data: FormData) => void; children: ReactNode }) {
  return <form className="form" onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); onSubmit(new FormData(event.currentTarget)); }}>{children}</form>;
}
