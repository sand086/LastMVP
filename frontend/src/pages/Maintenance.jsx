import { Wrench } from "lucide-react";

export default function Maintenance() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-mye-app p-6" data-testid="maintenance-page">
      <div className="max-w-lg w-full bg-white border border-mye-border rounded-lg p-10 space-y-6 animate-fade-in">
        <div className="inline-flex items-center gap-2 rounded-full bg-mye-accent-soft text-mye-accent px-3 py-1 text-xs font-mono uppercase tracking-wider">
          <Wrench className="h-3.5 w-3.5" /> Mantenimiento
        </div>
        <h1 className="text-3xl font-semibold tracking-tight text-mye-ink">
          Tu tenant está en mantenimiento.
        </h1>
        <p className="text-sm text-mye-ink-muted leading-relaxed">
          Estamos realizando ajustes para mejorar el servicio. La operación se reanudará automáticamente cuando
          finalicen los trabajos. Si tienes una emergencia operativa, contacta a tu administrador del tenant.
        </p>
        <div className="rounded-md border border-mye-border bg-mye-app px-4 py-3 text-xs font-mono text-mye-ink-muted">
          Solo el rol <span className="text-mye-ink">root_dev</span> puede acceder durante mantenimiento.
        </div>
      </div>
    </div>
  );
}
