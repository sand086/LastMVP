import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import { Loader2 } from "lucide-react";

export default function Default() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    let cancel = false;
    async function pickLanding() {
      if (!user) {
        navigate("/login", { replace: true });
        return;
      }
      try {
        const r = await api.get("/auth/redirect-target");
        if (cancel) return;
        const dest = r.data?.data?.redirect_to;
        if (dest && dest !== "/default") {
          navigate(dest, { replace: true });
        }
      } catch (_e) { /* stay on /default */ }
    }
    pickLanding();
    return () => { cancel = true; };
  }, [user, navigate]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-mye-app p-6" data-testid="default-page">
      <div className="max-w-md w-full bg-white border border-mye-border rounded-lg p-8 space-y-5 animate-fade-in">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
          <Loader2 className="h-3.5 w-3.5 animate-spin text-mye-accent" /> Resolviendo destino…
        </div>
        <h1 className="text-2xl font-semibold tracking-tight text-mye-ink">Bienvenido{user?.name ? `, ${user.name}` : ""}.</h1>
        <p className="text-sm text-mye-ink-muted leading-relaxed">
          Tu rol <span className="font-mono text-mye-ink">{user?.role || "—"}</span> aún no tiene un panel asignado en el MVP, o
          el destino no está disponible.
        </p>
        <div className="flex gap-2">
          <button
            onClick={() => navigate("/admin/cae")}
            className="rounded-md border border-mye-border bg-white px-3 py-2 text-sm hover:bg-mye-primary-soft transition-colors"
            data-testid="default-go-cae"
          >
            Ir a CAE Admin
          </button>
          <button
            onClick={async () => { await logout(); navigate("/login"); }}
            className="rounded-md bg-mye-primary px-3 py-2 text-sm text-white hover:brightness-110 transition"
            data-testid="default-logout"
          >
            Cerrar sesión
          </button>
        </div>
      </div>
    </div>
  );
}
