/**
 * Composer — bottom-of-detail input where the agent writes a comment / nota
 * interna / external comm. Includes CTA cards (canned responses) selectable
 * with a single click.
 *
 * Wired to POST /api/agent/tickets/{id}/comment.
 *
 * iter44: When `visibility === "external"`, exposes editable To / CC / BCC
 * pills pre-filled from the shipment recipient (and sender, if available).
 * Backend validates each address and rejects external sends without `to`.
 */
import { useEffect, useState } from "react";
import { Send, Lock, Mail, Sparkles, Type, X, Plus, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { toast } from "sonner";

const CTA_CARDS = [
  {
    id: "evidence_request",
    label: "Pedir evidencias",
    icon: "📷",
    body: "Hola, para poder avanzar con tu caso necesitamos que nos compartas: 1) foto del paquete con la guía visible, 2) foto del daño desde 2 ángulos, y 3) foto de la caja externa. Gracias.",
  },
  {
    id: "tracking_request",
    label: "Solicitar tracking",
    icon: "📦",
    body: "Hola, ¿podrías confirmarnos el número de guía del envío para localizarlo en el sistema del transportista? Si lo tienes, también una captura del último escaneo nos ayuda mucho.",
  },
  {
    id: "apology_refund",
    label: "Disculpa + reembolso",
    icon: "💳",
    body: "Lamentamos mucho la situación que viviste con tu envío. Procederemos con el reembolso correspondiente en las próximas 48 horas hábiles. Te avisaremos por este mismo canal cuando esté ejecutado.",
  },
  {
    id: "patience_carrier",
    label: "Esperando carrier",
    icon: "⏳",
    body: "Estamos en contacto con el transportista para resolver tu caso. Te tendremos noticias en menos de 24 horas. Gracias por tu paciencia.",
  },
];

const EMAIL_RX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Composer({ ticketId, onPosted, recipientEmail, senderEmail }) {
  const [body, setBody] = useState("");
  const [visibility, setVisibility] = useState("internal");
  const [busy, setBusy] = useState(false);
  const [to, setTo] = useState([]);
  const [cc, setCc] = useState([]);
  const [bcc, setBcc] = useState([]);

  // Pre-fill `to` con el correo del destinatario cuando el agente cambia a "external"
  useEffect(() => {
    if (visibility === "external" && to.length === 0 && recipientEmail
        && EMAIL_RX.test(recipientEmail)) {
      setTo([recipientEmail]);
    }
  }, [visibility, recipientEmail, to.length]);

  async function send() {
    if (!body.trim()) return;
    if (visibility === "external" && to.length === 0) {
      toast.error("Agregá al menos un destinatario en 'Para'");
      return;
    }
    setBusy(true);
    try {
      const payload = { body: body.trim(), visibility };
      if (visibility === "external") {
        payload.to = to;
        payload.cc = cc;
        payload.bcc = bcc;
      }
      await api.post(`/agent/tickets/${ticketId}/comment`, payload);
      toast.success(visibility === "internal"
        ? "Nota interna agregada al timeline"
        : `Email enviado a ${to.length} destinatario(s)`);
      setBody("");
      onPosted?.();
    } catch (e) {
      toast.error(e.response?.data?.errors?.[0]?.message || e.message);
    } finally { setBusy(false); }
  }

  function applyCta(cta) {
    setBody((prev) => prev ? `${prev}\n\n${cta.body}` : cta.body);
  }

  return (
    <div className="bg-white border border-mye-border rounded-lg p-3 space-y-3"
         data-testid="ticket-composer">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted">
        <Sparkles className="h-3.5 w-3.5 text-mye-accent" /> Respuestas rápidas
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {CTA_CARDS.map((cta) => (
          <button key={cta.id} onClick={() => applyCta(cta)}
                  className="rounded-md border border-mye-border bg-mye-app/40 px-2 py-2 text-left hover:bg-mye-primary-soft hover:border-mye-accent/40 transition group"
                  data-testid={`composer-cta-${cta.id}`}>
            <div className="text-base mb-0.5">{cta.icon}</div>
            <div className="text-[11px] font-medium leading-tight group-hover:text-mye-accent transition">{cta.label}</div>
          </button>
        ))}
      </div>

      <div className="flex items-center gap-1 border-b border-mye-border pb-2">
        <button onClick={() => setVisibility("internal")}
                className={"inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs transition " +
                  (visibility === "internal"
                    ? "bg-mye-primary-soft text-mye-ink"
                    : "text-mye-ink-muted hover:bg-mye-app")}
                data-testid="composer-tab-internal">
          <Lock className="h-3 w-3" /> Nota interna
        </button>
        <button onClick={() => setVisibility("external")}
                className={"inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs transition " +
                  (visibility === "external"
                    ? "bg-mye-primary-soft text-mye-ink"
                    : "text-mye-ink-muted hover:bg-mye-app")}
                data-testid="composer-tab-external">
          <Mail className="h-3 w-3" /> Comunicación cliente
        </button>
        <span className="ml-auto text-[10px] font-mono text-mye-ink-muted flex items-center gap-1">
          <Type className="h-3 w-3" /> {body.length} chars
        </span>
      </div>

      {visibility === "external" && (
        <EmailHeaders
          to={to} setTo={setTo}
          cc={cc} setCc={setCc}
          bcc={bcc} setBcc={setBcc}
          recipientEmail={recipientEmail}
          senderEmail={senderEmail}
        />
      )}

      <textarea value={body}
                onChange={(e) => setBody(e.target.value)}
                rows={3}
                placeholder={visibility === "internal"
                  ? "Nota visible solo para el equipo interno…"
                  : "Mensaje que verá el cliente…"}
                className="w-full resize-y rounded-md border border-mye-border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-mye-accent/30"
                data-testid="composer-body" />

      <div className="flex items-center gap-2">
        <button onClick={send}
                disabled={busy || !body.trim() || (visibility === "external" && to.length === 0)}
                className="ml-auto inline-flex items-center gap-1.5 rounded-md bg-mye-accent text-white px-3 py-1.5 text-xs hover:brightness-110 transition disabled:opacity-60"
                data-testid="composer-send">
          <Send className="h-3.5 w-3.5" />
          {busy ? "Enviando…" : visibility === "internal" ? "Agregar nota" : "Enviar al cliente"}
        </button>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// EmailHeaders — pills editables para To / CC / BCC con autocomplete suggestions
// ─────────────────────────────────────────────────────────────────────────
function EmailHeaders({ to, setTo, cc, setCc, bcc, setBcc, recipientEmail, senderEmail }) {
  const [showCc, setShowCc] = useState(false);
  const [showBcc, setShowBcc] = useState(false);

  // Sugerencias contextuales (recipient + sender del envío)
  const suggestions = [
    recipientEmail && EMAIL_RX.test(recipientEmail) ? {
      email: recipientEmail, label: "destinatario",
    } : null,
    senderEmail && EMAIL_RX.test(senderEmail) ? {
      email: senderEmail, label: "remitente",
    } : null,
  ].filter(Boolean);

  return (
    <div className="rounded-md border border-mye-accent/30 bg-mye-primary-soft/30 p-2 space-y-1.5"
         data-testid="composer-email-headers">
      <EmailField label="Para" testid="to" values={to} setValues={setTo}
                  required suggestions={suggestions} />
      {showCc ? (
        <EmailField label="CC" testid="cc" values={cc} setValues={setCc}
                    suggestions={suggestions} />
      ) : null}
      {showBcc ? (
        <EmailField label="CCO" testid="bcc" values={bcc} setValues={setBcc}
                    suggestions={suggestions} />
      ) : null}
      <div className="flex items-center gap-2 pt-0.5">
        {!showCc && (
          <button type="button" onClick={() => setShowCc(true)}
                  className="text-[10px] font-mono text-mye-accent hover:underline"
                  data-testid="composer-add-cc">+ CC</button>
        )}
        {!showBcc && (
          <button type="button" onClick={() => setShowBcc(true)}
                  className="text-[10px] font-mono text-mye-accent hover:underline"
                  data-testid="composer-add-bcc">+ CCO</button>
        )}
        {to.length === 0 && (
          <span className="ml-auto inline-flex items-center gap-1 text-[10px] font-mono text-status-escalated">
            <AlertCircle className="h-3 w-3" /> falta destinatario
          </span>
        )}
      </div>
    </div>
  );
}

function EmailField({ label, testid, values, setValues, required = false, suggestions = [] }) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");

  function commit() {
    const v = draft.trim().replace(/[,;]$/, "");
    if (!v) { setDraft(""); return; }
    if (!EMAIL_RX.test(v)) {
      setError("Email inválido");
      return;
    }
    if (values.includes(v)) { setDraft(""); setError(""); return; }
    setValues([...values, v]);
    setDraft("");
    setError("");
  }
  function onKeyDown(e) {
    if (e.key === "Enter" || e.key === "," || e.key === ";" || e.key === "Tab") {
      if (draft.trim()) {
        e.preventDefault();
        commit();
      }
    } else if (e.key === "Backspace" && !draft && values.length > 0) {
      setValues(values.slice(0, -1));
    }
  }
  function remove(idx) {
    setValues(values.filter((_, i) => i !== idx));
  }
  const unusedSuggestions = suggestions.filter((s) => !values.includes(s.email));

  return (
    <div data-testid={`composer-field-${testid}`}>
      <div className="flex items-start gap-2">
        <span className="mt-1 text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted w-10 flex-shrink-0">
          {label}{required && ":"}
        </span>
        <div className="flex-1 flex flex-wrap items-center gap-1 min-h-[26px] rounded-md border border-mye-border bg-white px-1.5 py-1 focus-within:ring-2 focus-within:ring-mye-accent/30">
          {values.map((em, idx) => (
            <span key={`${em}-${idx}`}
                  className="inline-flex items-center gap-1 rounded-full bg-mye-primary-soft px-2 py-0.5 text-[11px] font-mono"
                  data-testid={`composer-${testid}-pill-${idx}`}>
              {em}
              <button type="button" onClick={() => remove(idx)}
                      className="text-mye-ink-muted hover:text-status-escalated"
                      data-testid={`composer-${testid}-remove-${idx}`}>
                <X className="h-2.5 w-2.5" />
              </button>
            </span>
          ))}
          <input value={draft}
                 onChange={(e) => { setDraft(e.target.value); setError(""); }}
                 onKeyDown={onKeyDown}
                 onBlur={commit}
                 placeholder={values.length === 0 ? "correo@ejemplo.com" : ""}
                 className="flex-1 min-w-[140px] bg-transparent text-xs outline-none placeholder:text-mye-ink-muted/60"
                 data-testid={`composer-${testid}-input`} />
        </div>
      </div>
      {(error || unusedSuggestions.length > 0) && (
        <div className="flex items-center gap-2 pl-12 mt-0.5 min-h-[14px]">
          {error && <span className="text-[10px] text-status-escalated">{error}</span>}
          {!error && unusedSuggestions.map((s) => (
            <button key={s.email} type="button"
                    onClick={() => setValues([...values, s.email])}
                    className="inline-flex items-center gap-1 text-[10px] font-mono text-mye-accent hover:underline"
                    data-testid={`composer-${testid}-suggest-${s.label}`}>
              <Plus className="h-2.5 w-2.5" /> {s.email}
              <span className="text-mye-ink-muted">({s.label})</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
