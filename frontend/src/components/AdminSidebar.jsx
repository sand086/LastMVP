/**
 * AdminSidebar — Navegación lateral colapsable para módulos administrativos.
 *
 * Origen: hallazgo de usuario (Iter35) — el header horizontal de /admin/cae con
 * todos los links resulta apretado en pantallas estrechas y NO es escalable
 * cuando se agregan más features. Cambia la nav de horizontal en el header a
 * sidebar lateral izquierdo colapsable.
 *
 * Comportamiento:
 *   - Solo se renderiza en rutas administrativas (/admin/*, /torre, /dashboard,
 *     /heatmap, /reclamos*).
 *   - No se renderiza en /login, /agente, /maintenance, etc.
 *   - Estado colapsado/expandido persistido en localStorage.
 *   - Al estar expandido, aplica `padding-left: 240px` al `<body>` para
 *     desplazar todo el contenido. Colapsado: 56px. NO se renderiza: 0.
 *   - Items filtrados por rol: admin/superadmin ven todo; root_dev también ve
 *     Webhooks, Security y Platform Carriers; agent/supervisor solo ven los
 *     items relevantes a su rol (en sus rutas el sidebar no se renderiza).
 *   - Indicador visual del item activo (rayita izquierda + bg accent).
 *
 * NO modifica los headers existentes de cada pantalla — solo se monta global
 * en App.js y empuja el contenido. Los headers actuales seguirán mostrando
 * el breadcrumb SaaS + user + logout.
 */
import { useEffect, useMemo, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  Briefcase, BookOpen, Inbox, Ticket, Bell, Sparkles, Activity, Webhook,
  ShieldCheck, Truck, ChevronLeft, ChevronRight, LayoutDashboard,
  ClipboardList, Map, AtSign,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { SidebarUserMenu } from "@/components/SidebarUserMenu";

const STORAGE_KEY = "mye_admin_sidebar_collapsed_v1";

// Rutas en las que el sidebar SE MONTA. Cualquier otra ruta → no se renderiza
// (login, /agente, /maintenance, /default, etc.).
const ADMIN_PATH_PREFIXES = [
  "/admin/",
  "/torre",
  "/dashboard",
  "/heatmap",
  "/reclamos",
];

// Catálogo de items agrupados (Iter36).
// Orden intencional: el grupo "Operación diaria" arriba — primer item Dashboard
// es la landing por defecto post-login. Cada grupo respeta jerarquía visual.
// `legacyTestId` preserva los `data-testid="nav-*"` previos para no romper
// el tour ni tests existentes.
const NAV_GROUPS = [
  {
    id: "ops",
    label: "Operación diaria",
    roles: ["admin", "superadmin", "root_dev", "supervisor", "coordinator"],
    items: [
      { to: "/dashboard", label: "Dashboard", icon: ClipboardList,
        roles: ["admin", "superadmin", "root_dev", "supervisor", "coordinator"],
        legacyTestId: "nav-dashboard" },
      { to: "/torre", label: "Torre de Control", icon: Activity,
        roles: ["supervisor", "coordinator", "admin", "superadmin", "root_dev"],
        legacyTestId: "nav-torre" },
      { to: "/admin/tickets", label: "Casos", icon: Ticket,
        roles: ["admin", "superadmin", "root_dev"],
        legacyTestId: "nav-tickets" },
      { to: "/heatmap", label: "Heatmap", icon: Map,
        roles: ["admin", "superadmin", "root_dev", "supervisor", "coordinator"],
        legacyTestId: "nav-heatmap" },
    ],
  },
  {
    id: "config",
    label: "Configuración",
    roles: ["admin", "superadmin", "root_dev"],
    items: [
      { to: "/admin/jerarquia", label: "Jerarquía", icon: Briefcase,
        roles: ["admin", "superadmin", "root_dev"],
        legacyTestId: "nav-jerarquia" },
      { to: "/admin/catalogo", label: "Catálogo", icon: BookOpen,
        roles: ["admin", "superadmin", "root_dev"],
        legacyTestId: "nav-catalogo" },
      { to: "/admin/ingesta", label: "Ingesta", icon: Inbox,
        roles: ["admin", "superadmin", "root_dev"],
        legacyTestId: "nav-ingesta" },
      { to: "/admin/notificaciones", label: "Notificaciones", icon: Bell,
        roles: ["admin", "superadmin", "root_dev"],
        legacyTestId: "nav-notificaciones" },
      { to: "/admin/email-settings", label: "Credenciales Email", icon: AtSign,
        roles: ["admin", "superadmin", "root_dev"],
        legacyTestId: "nav-email-settings" },
    ],
  },
  {
    id: "intel",
    label: "Inteligencia + Integraciones",
    roles: ["admin", "superadmin", "root_dev"],
    items: [
      { to: "/admin/ai", label: "IA", icon: Sparkles,
        roles: ["admin", "superadmin", "root_dev"],
        legacyTestId: "nav-ai" },
      { to: "/admin/webhooks", label: "Webhooks", icon: Webhook,
        roles: ["superadmin", "root_dev"],
        legacyTestId: "nav-webhooks" },
    ],
  },
  {
    id: "platform",
    label: "Plataforma",
    roles: ["superadmin", "root_dev"],
    items: [
      { to: "/admin/cae", label: "Inicio CAE", icon: LayoutDashboard,
        roles: ["admin", "superadmin", "root_dev"],
        legacyTestId: "nav-cae" },
      { to: "/admin/security", label: "Security", icon: ShieldCheck,
        roles: ["root_dev"],
        legacyTestId: "nav-security" },
      { to: "/admin/platform/carriers", label: "Platform · Carriers", icon: Truck,
        roles: ["root_dev"],
        legacyTestId: "nav-platform-carriers" },
    ],
  },
];

function shouldRender(pathname) {
  return ADMIN_PATH_PREFIXES.some((p) => pathname.startsWith(p));
}

export function AdminSidebar() {
  const { user } = useAuth();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => {
    try { return localStorage.getItem(STORAGE_KEY) === "1"; }
    catch { return false; }
  });

  const visible = shouldRender(location.pathname) && !!user;

  // Aplica padding-left dinámico al body para que el contenido se desplace.
  useEffect(() => {
    if (!visible) {
      document.body.style.paddingLeft = "";
      return;
    }
    document.body.style.paddingLeft = collapsed ? "56px" : "224px";
    return () => { document.body.style.paddingLeft = ""; };
  }, [visible, collapsed]);

  // Persistencia.
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0"); }
    catch { /* quota or private mode */ }
  }, [collapsed]);

  // Filtrar grupos+items por rol del usuario. Un grupo con 0 items visibles
  // no se renderiza (ej: agent no verá ninguno).
  const visibleGroups = useMemo(() => {
    if (!user?.role) return [];
    return NAV_GROUPS
      .filter((g) => g.roles.includes(user.role))
      .map((g) => ({
        ...g,
        items: g.items.filter((it) => it.roles.includes(user.role)),
      }))
      .filter((g) => g.items.length > 0);
  }, [user?.role]);

  if (!visible || visibleGroups.length === 0) return null;

  return (
    <aside
      data-testid="admin-sidebar"
      aria-label="Navegación admin"
      className={
        "fixed top-0 left-0 h-screen z-30 bg-white border-r border-mye-border flex flex-col transition-[width] " +
        (collapsed ? "w-14" : "w-56")
      }
    >
      {/* Brand row */}
      <div className="flex items-center gap-2 px-3 py-3 border-b border-mye-border min-h-[56px]">
        <div className="h-8 w-8 rounded-md bg-mye-accent grid place-items-center text-white font-mono text-sm shrink-0">
          M
        </div>
        {!collapsed && (
          <div className="leading-tight overflow-hidden">
            <div className="font-semibold tracking-tight text-sm truncate">MyExcellence</div>
            <div className="font-mono text-[10px] text-mye-ink-muted truncate">Admin · v2.1</div>
          </div>
        )}
      </div>

      {/* Nav grupos */}
      <nav className="flex-1 overflow-y-auto py-2 px-2 space-y-3">
        {visibleGroups.map((g) => (
          <div key={g.id} data-testid={`sidebar-group-${g.id}`}>
            {!collapsed && (
              <div className="px-2 pb-1 pt-1 text-[9px] uppercase tracking-[0.18em] font-mono text-mye-ink-muted/70">
                {g.label}
              </div>
            )}
            {collapsed && (
              <div className="mx-2 my-1 border-t border-mye-border/40" aria-hidden />
            )}
            <div className="space-y-0.5">
              {g.items.map((it) => {
                const Icon = it.icon;
                return (
                  <NavLink
                    key={it.to}
                    to={it.to}
                    data-testid={it.legacyTestId || `sidebar-nav-${it.to.replace(/[^a-z0-9]+/gi, "-").replace(/^-|-$/g, "")}`}
                    title={collapsed ? it.label : undefined}
                    className={({ isActive }) =>
                      "group relative flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition " +
                      (isActive
                        ? "bg-mye-accent/10 text-mye-accent font-medium"
                        : "text-mye-ink-muted hover:bg-mye-bg hover:text-mye-ink")
                    }
                  >
                    {({ isActive }) => (
                      <>
                        {isActive && (
                          <span aria-hidden className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-mye-accent" />
                        )}
                        <Icon className="h-4 w-4 shrink-0" />
                        {!collapsed && <span className="truncate">{it.label}</span>}
                      </>
                    )}
                  </NavLink>
                );
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* User menu (avatar + dropdown con perfil, tour, salir) */}
      <SidebarUserMenu collapsed={collapsed} />

      {/* Collapse toggle */}
      <button
        type="button"
        onClick={() => setCollapsed((v) => !v)}
        data-testid="sidebar-toggle"
        aria-label={collapsed ? "Expandir menú" : "Colapsar menú"}
        className="border-t border-mye-border py-2 text-xs text-mye-ink-muted hover:text-mye-ink hover:bg-mye-bg inline-flex items-center justify-center gap-1.5"
      >
        {collapsed
          ? <ChevronRight className="h-4 w-4" />
          : <><ChevronLeft className="h-3.5 w-3.5" /> <span>Colapsar</span></>}
      </button>
    </aside>
  );
}

export default AdminSidebar;
