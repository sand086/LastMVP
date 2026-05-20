/**
 * SaaSHierarchyBreadcrumb — Bundle E · Parte 2 (Iter33).
 *
 * Muestra la jerarquía SaaS Platform → Tenant → Cliente para que el admin
 * entienda en todo momento qué pieza de la pirámide está editando.
 *
 * Hallazgo UX-PLATFORM-001 resuelto: la distinción Platform vs Tenant vs
 * Client NO se ve en la UI actual. Esto causa confusión cuando MyE rota
 * credenciales de carrier a nivel platform — el admin no entiende por qué su
 * carrier "de pronto cambió".
 *
 * Comportamiento:
 *   - 3 chips clickeables con tooltips explicativos.
 *   - Color y emoji distintivos por nivel.
 *   - Roles operativos (agent, supervisor) ven los chips de Platform y
 *     Tenant como informativos (sin acción), solo el chip de Cliente es
 *     navegable.
 *   - Admins/superadmins/root_dev pueden navegar a Tenant → /admin/jerarquia.
 *
 * Props:
 *   - clientName?: nombre del cliente actual (si la ruta tiene contexto)
 *   - onClientClick?: callback opcional para abrir selector
 *   - className?: extra clases para el contenedor
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Globe, Building2, Users, Info } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const TOOLTIPS = {
  platform: "MyExcellence es la plataforma SaaS, operada por Mensajería y Estrategias (M&E). Algunas configuraciones — credenciales de carrier a nivel plataforma — son gestionadas por el equipo de M&E. Cambios a este nivel pueden afectar a todos los tenants.",
  tenant: "Tu organización dentro de MyExcellence. Tenés control administrativo total sobre clientes, motivos, soluciones, permisos y notificaciones. Los usuarios de tu tenant solo ven datos de tu tenant.",
  client: "Cada cliente que tu organización gestiona (por ejemplo, una marca a la que le ofrecés servicios de logística). Los tickets, reclamos y guías pertenecen a un cliente específico.",
};

function Chip({ icon: Icon, label, color, tooltip, onClick, testId, informative }) {
  const [show, setShow] = useState(false);
  const interactive = !!onClick && !informative;
  return (
    <div
      className="relative inline-flex"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onFocus={() => setShow(true)}
      onBlur={() => setShow(false)}
    >
      <button
        type="button"
        onClick={interactive ? onClick : undefined}
        data-testid={testId}
        aria-label={label}
        className={[
          "inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-medium border transition",
          color,
          interactive ? "cursor-pointer hover:brightness-95" : "cursor-default",
        ].join(" ")}
      >
        <Icon className="h-3 w-3" />
        <span>{label}</span>
        {informative && <Info className="h-2.5 w-2.5 opacity-50" />}
      </button>
      {show && (
        <div
          role="tooltip"
          data-testid={`${testId}-tooltip`}
          className="absolute top-full left-0 mt-1 z-50 w-64 rounded-md bg-mye-ink text-white text-[11px] leading-relaxed p-2 shadow-lg pointer-events-none"
        >
          {tooltip}
        </div>
      )}
    </div>
  );
}

export function SaaSHierarchyBreadcrumb({
  clientName, onClientClick, className = "",
}) {
  const { user } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;

  const tenantName = user.tenant_name || user.tenant_slug || "Tu tenant";
  const isAdminish = ["admin", "superadmin", "root_dev"].includes(user.role);

  function goTenant() {
    if (isAdminish) navigate("/admin/jerarquia");
  }
  function goClient() {
    if (onClientClick) onClientClick();
    else if (isAdminish) navigate("/admin/jerarquia");
  }

  return (
    <nav
      aria-label="Jerarquía SaaS"
      data-testid="saas-hierarchy-breadcrumb"
      data-tour-target="hierarchy-breadcrumb"
      className={`inline-flex items-center gap-1 text-mye-ink ${className}`}
    >
      <Chip
        icon={Globe}
        label="MyExcellence"
        color="border-slate-300 bg-slate-50 text-slate-700"
        tooltip={TOOLTIPS.platform}
        testId="hierarchy-chip-platform"
        informative
      />
      <span className="text-mye-ink-muted text-xs" aria-hidden>›</span>
      <Chip
        icon={Building2}
        label={tenantName}
        color="border-mye-accent/30 bg-mye-accent/10 text-mye-accent"
        tooltip={TOOLTIPS.tenant}
        onClick={goTenant}
        testId="hierarchy-chip-tenant"
        informative={!isAdminish}
      />
      <span className="text-mye-ink-muted text-xs" aria-hidden>›</span>
      <Chip
        icon={Users}
        label={clientName || "Todos los clientes"}
        color="border-emerald-200 bg-emerald-50 text-emerald-700"
        tooltip={TOOLTIPS.client}
        onClick={goClient}
        testId="hierarchy-chip-client"
      />
    </nav>
  );
}

export default SaaSHierarchyBreadcrumb;
