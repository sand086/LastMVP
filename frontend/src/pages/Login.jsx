import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { ShieldCheck, AlertTriangle, Loader2 } from "lucide-react";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const loc = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const next = new URLSearchParams(loc.search).get("next");
  const reason = new URLSearchParams(loc.search).get("reason");

  async function onSubmit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    const r = await login(email.trim(), password);
    setBusy(false);
    if (!r.ok) {
      setError(r.error || "Credenciales inválidas.");
      return;
    }
    navigate(next ? decodeURIComponent(next) : (r.redirect || "/default"), { replace: true });
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.05fr_1fr]" data-testid="login-page">
      {/* Marca lateral */}
      <aside
        className="hidden lg:flex flex-col justify-between p-14 text-white relative overflow-hidden"
        style={{ background: "linear-gradient(180deg, hsl(var(--mye-primary)) 0%, hsl(var(--mye-sidebar)) 100%)" }}
      >
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-md bg-mye-accent grid place-items-center font-mono font-semibold">M</div>
          <div className="leading-tight">
            <div className="font-semibold tracking-tight text-lg">MyExcellence</div>
            <div className="font-mono text-xs opacity-70">v2.1-MVP</div>
          </div>
        </div>

        <div className="relative max-w-lg space-y-6 animate-fade-in">
          <div className="inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-mono text-white/60">
            <span className="h-px w-6 bg-mye-accent" /> Plataforma de gestión de incidencias
          </div>
          <h1 className="text-4xl xl:text-5xl font-semibold leading-tight tracking-tight">
            Cuando el envío<br />
            <span className="text-mye-accent">sale mal</span>, MyE toma el control.
          </h1>
          <p className="text-white/70 leading-relaxed">
            Mientras otras plataformas se construyen alrededor del envío, MyExcellence se construye alrededor de la
            <span className="text-white font-medium"> incidencia</span>. Detecta, decide, ejecuta — respetando los
            permisos contratados por cada cliente.
          </p>
          <div className="grid grid-cols-3 gap-3 pt-4">
            {[
              ["Multi-tenant", "Aislamiento duro"],
              ["LATAM-first", "es-MX nativo"],
              ["JSON-first", "API estándar"],
            ].map(([title, sub]) => (
              <div key={title} className="rounded-md border border-white/10 bg-white/5 px-3 py-2">
                <div className="font-mono text-[11px] uppercase tracking-wider text-mye-accent">{title}</div>
                <div className="text-xs text-white/70">{sub}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="font-mono text-xs text-white/40">
          Mensajería &amp; Estrategias · Innovación y Desarrollo · Confidencial
        </div>
      </aside>

      {/* Formulario */}
      <main className="flex items-center justify-center p-8 lg:p-14 bg-mye-app">
        <div className="w-full max-w-md space-y-8 animate-fade-in">
          <div>
            <div className="inline-flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] font-mono text-mye-ink-muted">
              <ShieldCheck className="h-3.5 w-3.5 text-mye-accent" /> Acceso operativo
            </div>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight text-mye-ink">Inicia sesión</h2>
            <p className="mt-1 text-sm text-mye-ink-muted">
              Usa la cuenta provisionada por tu administrador del tenant.
            </p>
          </div>

          {reason === "expired" && (
            <div
              className="rounded-md border border-mye-border bg-mye-accent-soft px-3 py-2 text-[13px] text-mye-ink"
              data-testid="login-session-expired"
            >
              Tu sesión expiró. Inicia sesión nuevamente para continuar.
            </div>
          )}

          <form onSubmit={onSubmit} className="space-y-4" data-testid="login-form">
            <label className="block">
              <span className="text-xs font-mono uppercase tracking-wider text-mye-ink-muted">Correo</span>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="root@myexcellence.local"
                autoComplete="username"
                className="mt-1 w-full rounded-md border border-mye-border bg-white px-3 py-2.5 text-sm outline-none transition-colors focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20"
                data-testid="login-email-input"
              />
            </label>

            <label className="block">
              <span className="text-xs font-mono uppercase tracking-wider text-mye-ink-muted">Contraseña</span>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                autoComplete="current-password"
                className="mt-1 w-full rounded-md border border-mye-border bg-white px-3 py-2.5 text-sm outline-none transition-colors focus:border-mye-accent focus:ring-2 focus:ring-mye-accent/20"
                data-testid="login-password-input"
              />
            </label>

            {error && (
              <div
                className="flex items-start gap-2 rounded-md border border-status-escalated/30 bg-status-escalated/5 px-3 py-2 text-[13px] text-status-escalated"
                data-testid="login-error"
              >
                <AlertTriangle className="h-4 w-4 mt-0.5 flex-none" />
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className="group inline-flex w-full items-center justify-center gap-2 rounded-md bg-mye-accent px-4 py-2.5 text-sm font-medium text-white transition-all duration-200 hover:brightness-110 active:translate-y-px disabled:opacity-60"
              data-testid="login-submit-button"
            >
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              {busy ? "Verificando…" : "Entrar"}
            </button>
          </form>

          <div className="text-xs text-mye-ink-muted leading-relaxed border-t border-mye-border pt-5">
            <div className="font-mono uppercase tracking-wider mb-1 text-[10px]">Cuenta seed (development)</div>
            root@myexcellence.local · Admin123!
          </div>
        </div>
      </main>
    </div>
  );
}
