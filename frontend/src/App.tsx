import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Shell from "./components/Shell";
import { Loading } from "./components/ui";
import AdminPage from "./pages/AdminPage";
import AuthCallback from "./pages/AuthCallback";
import BudgetsPage from "./pages/BudgetsPage";
import Dashboard from "./pages/Dashboard";
import DocumentsPage from "./pages/DocumentsPage";
import LoginPage from "./pages/LoginPage";
import LookupPage from "./pages/LookupPage";
import RecordPage from "./pages/RecordPage";
import RequisitionsPage from "./pages/RequisitionsPage";
import SettingsPage from "./pages/SettingsPage";
import SourcingPage from "./pages/SourcingPage";
import SuppliersPage from "./pages/SuppliersPage";

function Protected() { const { session, ready } = useAuth(); if (!ready) return <main className="center-page"><Loading/></main>; return session ? <Shell/> : <Navigate to="/login" replace/>; }

export default function App() {
  return <Routes>
    <Route path="/login" element={<LoginPage/>}/><Route path="/auth/callback" element={<AuthCallback/>}/>
    <Route element={<Protected/>}>
      <Route index element={<Dashboard/>}/><Route path="requisitions" element={<RequisitionsPage/>}/><Route path="requisitions/:id" element={<RecordAlias type="requisition"/>}/>
      <Route path="suppliers" element={<SuppliersPage/>}/><Route path="sourcing" element={<SourcingPage/>}/><Route path="sourcing/:id" element={<RecordAlias type="rfq"/>}/>
      <Route path="documents" element={<DocumentsPage/>}/><Route path="budgets" element={<BudgetsPage/>}/><Route path="admin" element={<AdminPage/>}/><Route path="settings" element={<SettingsPage/>}/>
      <Route path="evaluations" element={<LookupPage kind="evaluations"/>}/><Route path="awards" element={<LookupPage kind="awards"/>}/><Route path="operations" element={<LookupPage kind="operations"/>}/>
      <Route path="record/:type/:id" element={<RecordPage/>}/><Route path="*" element={<Navigate to="/" replace/>}/>
    </Route>
  </Routes>;
}

function RecordAlias({ type }: { type: string }) { const id = window.location.pathname.split("/").at(-1); return <Navigate to={`/record/${type}/${id}`} replace/>; }
