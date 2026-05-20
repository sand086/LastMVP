/**
 * WhatsAppPanel — conversación bidireccional inline en ticket detail (PROMPT 21).
 */
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Send, MessageCircle, RefreshCw, AlertTriangle } from "lucide-react";

export default function WhatsAppPanel({ ticketId, clientPhone }) {
  const [items, setItems] = useState([]);
  const [text, setText] = useState("");
  const [to, setTo] = useState(clientPhone || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const bottomRef = useRef(null);

  async function refresh() {
    if (!ticketId) return;
    try {
      const r = await api.get(`/tickets/${ticketId}/whatsapp`);
      setItems(r.data?.data?.items || []);
    } catch (e) { /* silent */ }
  }

  useEffect(() => { refresh(); const id = setInterval(refresh, 15000); return () => clearInterval(id); }, [ticketId]);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [items.length]);

  async function send() {
    if (!text.trim() || !to.match(/^\+\d{8,15}$/)) {
      setErr("Número inválido (E.164) o mensaje vacío.");
      return;
    }
    setBusy(true); setErr(null);
    try {
      await api.post("/admin/whatsapp/send", { to, text: text.trim(), ticket_id: ticketId });
      setText("");
      await refresh();
    } catch (e) {
      setErr(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  return (
    <div className="bg-white border border-mye-border rounded-md overflow-hidden" data-testid="whatsapp-panel">
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-mye-border bg-mye-app/40">
        <div className="flex items-center gap-2 font-medium text-sm">
          <MessageCircle className="h-4 w-4 text-mye-accent" /> WhatsApp · {items.length} mensajes
        </div>
        <button onClick={refresh} className="text-mye-ink-muted hover:text-mye-ink"
                data-testid="whatsapp-refresh">
          <RefreshCw className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="p-3 space-y-1 max-h-[320px] overflow-y-auto bg-mye-app/20" data-testid="whatsapp-thread">
        {items.length === 0 && (
          <div className="text-center py-8 text-xs font-mono text-mye-ink-muted">
            Sin mensajes en este ticket todavía.
          </div>
        )}
        {items.map((m) => (
          <div key={m.id} className={"flex " + (m.direction === "outbound" ? "justify-end" : "justify-start")}
               data-testid={`whatsapp-msg-${m.direction}`}>
            <div className={"max-w-[75%] rounded-lg px-3 py-1.5 text-sm " +
              (m.direction === "outbound"
                ? "bg-mye-accent/10 border border-mye-accent/30 text-mye-ink"
                : "bg-white border border-mye-border")}>
              <div>{m.text || (m.media_type ? `[${m.media_type}] ${m.media_url || ""}` : "—")}</div>
              <div className="text-[9px] font-mono text-mye-ink-muted mt-1 flex justify-between gap-2">
                <span>{m.created_at?.slice(11, 16)}</span>
                {m.mocked && <span className="text-mye-accent">MOCKED</span>}
                <span>{m.status}</span>
              </div>
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-mye-border p-3 space-y-2">
        {err && (
          <div className="flex items-start gap-2 rounded border border-status-escalated/30 bg-status-escalated/5 px-2 py-1 text-[12px] text-status-escalated">
            <AlertTriangle className="h-3.5 w-3.5 mt-0.5" /> {err}
          </div>
        )}
        <div className="flex gap-2">
          <input value={to} onChange={(e) => setTo(e.target.value)}
                 placeholder="+5215512345678"
                 className="w-44 rounded-md border border-mye-border bg-white px-2 py-1.5 text-xs font-mono"
                 data-testid="whatsapp-to" />
          <input value={text} onChange={(e) => setText(e.target.value)}
                 onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !busy) { e.preventDefault(); send(); } }}
                 placeholder="Escribe tu mensaje…"
                 className="flex-1 rounded-md border border-mye-border bg-white px-3 py-1.5 text-sm"
                 data-testid="whatsapp-text" />
          <button onClick={send} disabled={busy || !text.trim()}
                  className="inline-flex items-center gap-1 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition disabled:opacity-60"
                  data-testid="whatsapp-send">
            <Send className="h-3.5 w-3.5" /> {busy ? "Enviando…" : "Enviar"}
          </button>
        </div>
      </div>
    </div>
  );
}
