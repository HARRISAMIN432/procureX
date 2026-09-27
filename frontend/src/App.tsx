import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Shell from "./components/Shell";
import { Loading } from "./components/ui";
import AdminPage from "./pages/AdminPage";
import AuthCallback from "./pages/AuthCallback";
import BudgetsPage from "./pages/BudgetsPage";
import Dashboard from "./pages/Dashboard";
import DocumentsPage from "./pages/DocumentsPage";
import DocumentDetailPage from "./pages/DocumentDetailPage";
import LoginPage from "./pages/LoginPage";
import LookupPage from "./pages/LookupPage";
import RecordPage from "./pages/RecordPage";
import RequisitionsPage from "./pages/RequisitionsPage";
import RequisitionDetailPage from "./pages/RequisitionDetailPage";
import RfqDetailPage from "./pages/RfqDetailPage";
import ApprovalsPage from "./pages/ApprovalsPage";
import SettingsPage from "./pages/SettingsPage";
import CommercialPage from "./pages/CommercialPage";
import LegalPage from "./pages/LegalPage";
import SourcingPage from "./pages/SourcingPage";
import SuppliersPage from "./pages/SuppliersPage";
import SupplierPortalPage from "./pages/SupplierPortalPage";
import SupplierOrderPage from "./pages/SupplierOrderPage";
import WorkspacePage from "./pages/WorkspacePage";

function Protected() { const { session, ready, authenticated } = useAuth(); if (!ready) return <main className="center-page"><Loading/></main>; return session ? <Shell/> : <Navigate to={authenticated ? "/workspaces" : "/login"} replace/>; }

export default function App() {
  return <Routes>
    <Route path="/login" element={<LoginPage/>}/><Route path="/auth/callback" element={<AuthCallback/>}/><Route path="/workspaces" element={<WorkspacePage/>}/><Route path="/legal/:document" element={<LegalPage/>}/>
    <Route path="/supplier/invitations/:organizationId/:invitationId" element={<SupplierPortalPage/>}/>
    <Route path="/supplier/orders/:organizationId/:purchaseOrderId" element={<SupplierOrderPage/>}/>
    <Route element={<Protected/>}>
      <Route index element={<Dashboard/>}/><Route path="requisitions" element={<RequisitionsPage/>}/><Route path="requisitions/:id" element={<RequisitionDetailPage/>}/>
      <Route path="suppliers" element={<SuppliersPage/>}/><Route path="sourcing" element={<SourcingPage/>}/><Route path="sourcing/:id" element={<RfqDetailPage/>}/><Route path="approvals" element={<ApprovalsPage/>}/>
      <Route path="documents" element={<DocumentsPage/>}/><Route path="documents/:id" element={<DocumentDetailPage/>}/><Route path="budgets" element={<BudgetsPage/>}/><Route path="admin" element={<AdminPage/>}/><Route path="settings" element={<SettingsPage/>}/>
      <Route path="service" element={<CommercialPage/>}/>
      <Route path="evaluations" element={<LookupPage kind="evaluations"/>}/><Route path="awards" element={<LookupPage kind="awards"/>}/><Route path="operations" element={<LookupPage kind="operations"/>}/>
      <Route path="record/:type/:id" element={<RecordPage/>}/><Route path="*" element={<Navigate to="/" replace/>}/>
    </Route>
  </Routes>;
}
