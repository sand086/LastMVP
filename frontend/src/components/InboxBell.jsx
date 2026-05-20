/**
 * InboxBell — campana de notificaciones in-app (PROMPT 13 P1.2).
 * Polls /api/inbox/unread-count cada 30s. Click → dropdown con últimos 10.
 * Click en item → mark-read + navega al `link` si existe.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, CheckCheck } from "lucide-react";
import { api } from "@/lib/api";

const POLL_MS = 30000;

function timeAgo(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const s = Math.max(0, Math.floor((Date.now() - d.getTime()) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  return `${Math.floor(h / 24)}d`;
}

export default function InboxBell() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const wrapRef = useRef(null);

  const refreshCount = useCallback(async () => {
    try {
      const r = await api.get("/inbox/unread-count");
      setUnread(r.data?.data?.unread ?? 0);
    } catch (_) { /* silent */ }
  }, []);

  const refreshList = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get("/inbox", { params: { limit: 10 } });
      setItems(r.data?.data?.items ?? []);
    } catch (_) {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  // Poll unread count
  useEffect(() => {
    refreshCount();
    const id = setInterval(refreshCount, POLL_MS);
    return () => clearInterval(id);
  }, [refreshCount]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const handleToggle = async () => {
    const next = !open;
    setOpen(next);
    if (next) await refreshList();
  };

  const handleItemClick = async (item) => {
    if (!item.read_at) {
      try {
        await api.post(`/inbox/${item.id}/read`);
      } catch (_) { /* ignore */ }
    }
    setOpen(false);
    await refreshCount();
    if (item.link) {
      navigate(item.link);
    }
  };

  const handleMarkAll = async () => {
    try {
      await api.post("/inbox/read-all");
      await Promise.all([refreshCount(), refreshList()]);
    } catch (_) { /* ignore */ }
  };

  return (
    <div ref={wrapRef} className="relative" data-testid="inbox-bell">
      <button
        onClick={handleToggle}
        className="relative inline-flex items-center justify-center rounded-md border border-mye-border bg-white h-8 w-8 hover:bg-mye-primary-soft transition"
        aria-label="Notificaciones"
        data-testid="inbox-bell-trigger"
      >
        <Bell className="h-3.5 w-3.5 text-mye-ink" />
        {unread > 0 && (
          <span
            className="absolute -top-1 -right-1 min-w-[16px] h-[16px] px-1 rounded-full bg-mye-accent text-white text-[10px] font-mono font-semibold flex items-center justify-center leading-none"
            data-testid="inbox-bell-badge"
          >
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          className="absolute right-0 mt-2 w-[340px] rounded-md border border-mye-border bg-white shadow-lg z-50 overflow-hidden"
          data-testid="inbox-bell-panel"
        >
          <div className="flex items-center justify-between px-3 py-2 border-b border-mye-border bg-mye-app/40">
            <div className="text-xs font-medium text-mye-ink">Notificaciones</div>
            {unread > 0 && (
              <button
                onClick={handleMarkAll}
                className="inline-flex items-center gap-1 text-[10px] font-mono text-mye-ink-muted hover:text-mye-accent"
                data-testid="inbox-bell-mark-all"
              >
                <CheckCheck className="h-3 w-3" /> Marcar todas
              </button>
            )}
          </div>

          <div className="max-h-[360px] overflow-y-auto">
            {loading ? (
              <div className="px-3 py-6 text-center text-xs font-mono text-mye-ink-muted">Cargando…</div>
            ) : items.length === 0 ? (
              <div className="px-3 py-6 text-center text-xs font-mono text-mye-ink-muted" data-testid="inbox-bell-empty">
                Sin notificaciones
              </div>
            ) : (
              <ul className="divide-y divide-mye-border">
                {items.map((it) => (
                  <li key={it.id}>
                    <button
                      onClick={() => handleItemClick(it)}
                      className={"w-full text-left px-3 py-2.5 hover:bg-mye-primary-soft transition " +
                        (it.read_at ? "" : "bg-mye-accent/5")}
                      data-testid={`inbox-bell-item-${it.id}`}
                    >
                      <div className="flex items-start gap-2">
                        {!it.read_at && (
                          <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-mye-accent shrink-0" />
                        )}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-baseline justify-between gap-2">
                            <div className="text-xs font-medium text-mye-ink truncate">{it.title}</div>
                            <div className="text-[10px] font-mono text-mye-ink-muted shrink-0">{timeAgo(it.created_at)}</div>
                          </div>
                          {it.body && (
                            <div className="text-[11px] text-mye-ink-muted mt-0.5 line-clamp-2">{it.body}</div>
                          )}
                          {it.kind && (
                            <div className="mt-1 inline-block text-[9px] font-mono uppercase tracking-wider text-mye-ink-muted">
                              {it.kind}
                            </div>
                          )}
                        </div>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
