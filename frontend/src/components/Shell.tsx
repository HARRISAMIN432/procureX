import { useQuery } from "@tanstack/react-query";
import { Archive, Banknote, Bell, BookOpenCheck, Building2, ChevronDown, CircleGauge, ClipboardList, FileSearch, LogOut, Menu, PackageCheck, PanelLeftClose, Search, Settings, ShieldCheck, Store, Users, X } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useState } from "react";
import { useAuth, useSession } from "../auth/AuthContext";
import { api } from "../lib/api";
import { initials } from "../lib/format";
import type { MembershipContext, Organization } from "../types";

const nav = [
  ["Overview", "/", CircleGauge], ["Requisitions", "/requisitions", ClipboardList], ["Sourcing", "/sourcing", FileSearch],
  ["Suppliers", "/suppliers", Store], ["Documents", "/documents", Archive], ["Evaluations", "/evaluations", BookOpenCheck],
  ["Awards", "/awards", ShieldCheck], ["Orders", "/operations", PackageCheck], ["Budgets", "/budgets", Banknote],
  ["Team & access", "/admin", Users], ["Settings", "/settings", Settings],
] as const;

export default function Shell() {
  const { logout } = useAuth();
  const session = useSession();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const org = useQuery({ queryKey: ["organization", session.organizationId], queryFn: () => api<Organization>(session, "/api/v1/organizations/current") });
  const membership = useQuery({ queryKey: ["membership", session.organizationId], queryFn: () => api<MembershipContext>(session, "/api/v1/organizations/current/membership") });
  const current = nav.find(([, path]) => path === "/" ? location.pathname === "/" : location.pathname.startsWith(path));
  return <div className={`app-shell ${collapsed ? "nav-collapsed" : ""}`}>
    <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`}>
      <div className="brand"><div className="brand-mark">PX</div><div className="brand-copy"><strong>ProcureX</strong><span>Control workspace</span></div><button className="icon-button mobile-only" onClick={() => setMobileOpen(false)} aria-label="Close navigation"><X size={19}/></button></div>
      <div className="workspace-switch"><Building2 size={17}/><div><small>Workspace</small><strong>{org.data?.name || "Loading…"}</strong></div><ChevronDown size={15}/></div>
      <nav aria-label="Primary navigation">{nav.map(([label, path, Icon]) => <NavLink key={path} to={path} end={path === "/"} onClick={() => setMobileOpen(false)}><Icon size={18}/><span>{label}</span></NavLink>)}</nav>
      <div className="sidebar-foot"><button onClick={() => setCollapsed(!collapsed)} className="sidebar-control"><PanelLeftClose size={17}/><span>Collapse navigation</span></button><button onClick={() => void logout()} className="sidebar-control"><LogOut size={17}/><span>Sign out</span></button></div>
    </aside>
    <main className="main-area">
      <header className="topbar"><button className="icon-button mobile-menu" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu size={20}/></button><div className="breadcrumb"><span>ProcureX</span><b>/</b><strong>{current?.[0] || "Workspace"}</strong></div><div className="topbar-actions"><button className="search-trigger"><Search size={16}/><span>Search records</span><kbd>⌘ K</kbd></button><button className="icon-button" aria-label="Notifications"><Bell size={18}/></button><div className="user-chip"><span>{initials(session.displayName)}</span><div><strong>{session.displayName}</strong><small>{membership.data?.permissions.length ?? 0} permissions</small></div></div></div></header>
      <div className="page"><Outlet /></div>
    </main>
    {mobileOpen && <button className="mobile-scrim" onClick={() => setMobileOpen(false)} aria-label="Close navigation"/>}
  </div>;
}
