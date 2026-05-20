/**
 * SidebarUserMenu — Avatar + menú de usuario en el fondo del AdminSidebar.
 *
 * Reemplaza el bloque "user/email + InboxBell + Salir" que cada pantalla admin
 * tenía en su topbar (Iter38). El menú aparece justo encima del toggle Colapsar
 * y consolida en un solo lugar:
 *   - email + rol
 *   - "Reabrir asistente de configuración" (solo admin/superadmin/root_dev)
 *   - "Volver a hacer el tour" (cualquier rol con tour disponible)
 *   - "Cerrar sesión"
 *
 * Estado dropdown abre hacia arriba (top-full bottom-auto reverso) para no
 * salirse de pantalla. Click fuera lo cierra.
 *
 * Props:
 *   - collapsed: estado del sidebar; en modo colapsado solo se muestra el
 *     avatar (iniciales).
 */
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LogOut, Sparkles, BookOpen, ChevronUp } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

function initialsFromEmail(email) {
  if (!email) return "?";
  const local = email.split("@")[0] || "";
  // intentar nombre.apellido → "NA", caer en primeras 2 letras.
  const parts = local.split(/[._-]/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return local.slice(0, 2).toUpperCase();
}

export function SidebarUserMenu({ collapsed = false }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function onDoc(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    if (open) {
      document.addEventListener("mousedown", onDoc);
      return () => document.removeEventListener("mousedown", onDoc);
    }
  }, [open]);

  if (!user) return null;
  const initials = initialsFromEmail(user.email);
  const isAdminish = ["admin", "superadmin", "root_dev"].includes(user.role);

  async function handleLogout() {
    setOpen(false);
    await logout();
    navigate("/login");
  }

  function handleReopenOnboarding() {
    setOpen(false);
    if (typeof window.__myeOpenOnboarding === "function") {
      window.__myeOpenOnboarding();
    }
  }

  function handleReplayTour() {
    setOpen(false);
    if (typeof window.__myeReplayTour === "function") {
      window.__myeReplayTour();
    }
  }

  return (
    <div className="relative border-t border-mye-border" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        data-testid="sidebar-user-menu-trigger"
        aria-haspopup="menu"
        aria-expanded={open}
        title={collapsed ? `${user.email} · ${user.role}` : undefined}
        className={
          "w-full flex items-center gap-2 px-2 py-2 text-left hover:bg-mye-bg transition " +
          (collapsed ? "justify-center" : "")
        }
      >
        <div
          aria-hidden
          className="h-8 w-8 shrink-0 rounded-full bg-mye-accent text-white grid place-items-center font-mono text-xs"
        >
          {initials}
        </div>
        {!collapsed && (
          <>
            <div className="min-w-0 flex-1 leading-tight">
              <div className="text-xs font-medium text-mye-ink truncate" data-testid="sidebar-user-email">
                {user.email}
              </div>
              <div className="text-[10px] font-mono text-mye-ink-muted truncate" data-testid="sidebar-user-role">
                {user.role}
              </div>
            </div>
            <ChevronUp
              className={"h-3.5 w-3.5 text-mye-ink-muted transition-transform " + (open ? "" : "rotate-180")}
            />
          </>
        )}
      </button>

      {open && (
        <div
          role="menu"
          data-testid="sidebar-user-menu"
          className="absolute bottom-full left-2 right-2 mb-1 bg-white border border-mye-border rounded-md shadow-lg overflow-hidden z-40"
          style={collapsed ? { left: "calc(100% + 4px)", right: "auto", minWidth: "220px", bottom: 0 } : undefined}
        >
          {collapsed && (
            <div className="px-3 py-2 border-b border-mye-border bg-mye-bg">
              <div className="text-xs font-medium text-mye-ink truncate">{user.email}</div>
              <div className="text-[10px] font-mono text-mye-ink-muted truncate">{user.role}</div>
            </div>
          )}
          {isAdminish && (
            <button
              type="button"
              onClick={handleReopenOnboarding}
              data-testid="sidebar-menu-onboarding"
              className="w-full text-left px-3 py-2 text-xs text-mye-ink hover:bg-mye-bg inline-flex items-center gap-2"
            >
              <BookOpen className="h-3.5 w-3.5 text-mye-accent" />
              Reabrir asistente de configuración
            </button>
          )}
          <button
            type="button"
            onClick={handleReplayTour}
            data-testid="sidebar-menu-tour"
            className="w-full text-left px-3 py-2 text-xs text-mye-ink hover:bg-mye-bg inline-flex items-center gap-2"
          >
            <Sparkles className="h-3.5 w-3.5 text-mye-accent" />
            Volver a hacer el tour
          </button>
          <button
            type="button"
            onClick={handleLogout}
            data-testid="sidebar-menu-logout"
            className="w-full text-left px-3 py-2 text-xs text-mye-ink hover:bg-status-escalated/10 hover:text-status-escalated border-t border-mye-border inline-flex items-center gap-2"
          >
            <LogOut className="h-3.5 w-3.5" />
            Cerrar sesión
          </button>
        </div>
      )}
    </div>
  );
}

export default SidebarUserMenu;
