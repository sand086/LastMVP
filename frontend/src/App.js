import "@/index.css";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/contexts/AuthContext";
import ProtectedRoute from "@/components/ProtectedRoute";
import Login from "@/pages/Login";
import Default from "@/pages/Default";
import Maintenance from "@/pages/Maintenance";
import AdminCAEHome from "@/pages/AdminCAEHome";
import AdminHierarchy from "@/pages/AdminHierarchy";
import AdminCatalog from "@/pages/AdminCatalog";
import AdminIngest from "@/pages/AdminIngest";
import AdminNotifications from "@/pages/AdminNotifications";
import AdminEmailSettings from "@/pages/AdminEmailSettings";
import AdminEmailTemplates from "@/pages/AdminEmailTemplates";
import AdminTickets, { TicketDetail } from "@/pages/AdminTickets";
import AdminAI from "@/pages/AdminAI";
import AdminWebhooks from "@/pages/AdminWebhooks";
import AdminSecurity from "@/pages/AdminSecurity";
import AdminPlatformCarriers from "@/pages/AdminPlatformCarriers";
import AuditorPanel from "@/pages/AuditorPanel";
import Heatmap from "@/pages/Heatmap";
import Reclamos, { ReclamoDetail } from "@/pages/Reclamos";
import AgentPanel from "@/pages/AgentPanel";
import ControlTower from "@/pages/ControlTower";
import Dashboard from "@/pages/Dashboard";
import { OnboardingProvider } from "@/onboarding/OnboardingProvider";
import { OnboardingWizard } from "@/admin/onboarding/OnboardingWizard";
import { AdminSidebar } from "@/components/AdminSidebar";

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Toaster richColors position="top-right" closeButton expand={false}
                  toastOptions={{ className: "font-mono text-xs" }} />
        <OnboardingProvider />
        <OnboardingWizard />
        <AdminSidebar />
        <Routes>
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="/login" element={<Login />} />
          <Route path="/maintenance" element={<Maintenance />} />
          <Route path="/default" element={<ProtectedRoute><Default /></ProtectedRoute>} />
          <Route path="/agente" element={<ProtectedRoute allow={["agent","supervisor","coordinator","admin","superadmin","root_dev"]}><AgentPanel /></ProtectedRoute>} />
          <Route path="/agente/:ticketId" element={<ProtectedRoute allow={["agent","supervisor","coordinator","admin","superadmin","root_dev"]}><AgentPanel /></ProtectedRoute>} />
          <Route path="/torre" element={<ProtectedRoute allow={["supervisor","coordinator","admin","superadmin","root_dev"]}><ControlTower /></ProtectedRoute>} />
          <Route path="/dashboard" element={<ProtectedRoute allow={["supervisor","coordinator","admin","superadmin","root_dev"]}><Dashboard /></ProtectedRoute>} />
          <Route path="/admin/cae"
                 element={<ProtectedRoute allow={["root_dev", "superadmin", "admin"]}><AdminCAEHome /></ProtectedRoute>} />
          <Route path="/admin/jerarquia"
                 element={<ProtectedRoute allow={["root_dev", "superadmin", "admin", "coordinator"]}><AdminHierarchy /></ProtectedRoute>} />
          <Route path="/admin/catalogo"
                 element={<ProtectedRoute allow={["root_dev", "superadmin", "admin", "coordinator"]}><AdminCatalog /></ProtectedRoute>} />
          <Route path="/admin/ingesta"
                 element={<ProtectedRoute allow={["root_dev", "superadmin", "admin"]}><AdminIngest /></ProtectedRoute>} />
          <Route path="/admin/notificaciones"
                 element={<ProtectedRoute allow={["root_dev", "superadmin", "admin"]}><AdminNotifications /></ProtectedRoute>} />
          <Route path="/admin/email-settings"
                 element={<ProtectedRoute allow={["root_dev", "superadmin", "admin"]}><AdminEmailSettings /></ProtectedRoute>} />
          <Route path="/admin/email-templates"
                 element={<ProtectedRoute allow={["root_dev", "superadmin", "admin"]}><AdminEmailTemplates /></ProtectedRoute>} />
          <Route path="/admin/tickets"
                 element={<ProtectedRoute allow={["root_dev", "superadmin", "admin", "coordinator", "supervisor"]}><AdminTickets /></ProtectedRoute>} />
          <Route path="/admin/tickets/:id"
                 element={<ProtectedRoute allow={["root_dev", "superadmin", "admin", "coordinator", "supervisor"]}><TicketDetail /></ProtectedRoute>} />
          <Route path="/admin/ai"
                 element={<ProtectedRoute allow={["root_dev", "superadmin", "admin"]}><AdminAI /></ProtectedRoute>} />
          <Route path="/admin/webhooks"
                 element={<ProtectedRoute allow={["root_dev", "superadmin", "admin"]}><AdminWebhooks /></ProtectedRoute>} />
          <Route path="/admin/security"
                 element={<ProtectedRoute allow={["root_dev", "superadmin"]}><AdminSecurity /></ProtectedRoute>} />
          <Route path="/admin/platform/carriers"
                 element={<ProtectedRoute allow={["root_dev", "superadmin"]}><AdminPlatformCarriers /></ProtectedRoute>} />
          <Route path="/auditor"
                 element={<ProtectedRoute allow={["client_auditor", "client_viewer", "root_dev", "superadmin"]}><AuditorPanel /></ProtectedRoute>} />
          <Route path="/heatmap"
                 element={<ProtectedRoute allow={["root_dev", "superadmin", "admin", "coordinator", "supervisor", "agent"]}><Heatmap /></ProtectedRoute>} />
          <Route path="/reclamos"
                 element={<ProtectedRoute allow={["root_dev", "superadmin", "admin", "coordinator", "supervisor", "agent"]}><Reclamos /></ProtectedRoute>} />
          <Route path="/reclamos/:id"
                 element={<ProtectedRoute allow={["root_dev", "superadmin", "admin", "coordinator", "supervisor", "agent"]}><ReclamoDetail /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/default" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}

export default App;
