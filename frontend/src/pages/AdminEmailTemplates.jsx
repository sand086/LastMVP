/**
 * AdminEmailTemplates — Iter55 P3.3.
 *
 * Editor por tenant de las plantillas de correo:
 *  - 8 nuevas por incident_type × variant (iter54)
 *  - 2 legacy (incident_notice, test_email)
 *
 * Cada plantilla se compone de:
 *  - Subject (1 línea)
 *  - HTML body
 *  - Text body (fallback plain text)
 *
 * Variables disponibles renderizadas via {{var}} (lista mostrada al editor).
 */
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Mail, Save, Eye, RotateCcw, Trash2 } from "lucide-react";

import { api } from "@/lib/api";
import { SaaSHierarchyBreadcrumb } from "@/components/SaaSHierarchyBreadcrumb";

// Label legibles para las keys (subset al doc del cliente)
const KEY_LABELS = {
  incident_address_issue_contacted:    "Dirección · contactado",
  incident_address_issue_no_contact:   "Dirección · sin contacto",
  incident_refused_confirmed:          "Rechazo · confirmado",
  incident_refused_not_confirmed:      "Rechazo · no confirmado",
  incident_refused_no_contact:         "Rechazo · sin contacto",
  incident_recipient_absent_contacted: "Ausente · contactado",
  incident_recipient_absent_no_contact:"Ausente · sin contacto",
  final_return_to_origin:              "Retorno a origen (final)",
  incident_notice:                     "Genérico (legacy)",
  test_email:                          "Prueba",
};

const DEFAULT_TEMPLATES = {
  incident_address_issue_contacted: {
    subject: "[Incidencia] Dirección validada — {{tracking_id}}",
    html_body: "<p>Hola {{recipient_name}},</p><p>Te comento acerca de la guía <b>{{tracking_id}}</b>. {{carrier_name}} notificó <b>{{incidence_label}}</b> en un intento de entrega. Validamos la información y se solicitaron referencias al destinatario para coordinar un nuevo intento. Se gestiona envío y te mantengo al tanto.</p><p>— {{operator_name}}</p>",
    text_body: "Hola {{recipient_name}}, validamos la dirección con el destinatario y se gestiona nuevo intento de entrega para la guía {{tracking_id}}.",
  },
  incident_address_issue_no_contact: {
    subject: "[Incidencia] Dirección — solicitamos apoyo {{tracking_id}}",
    html_body: "<p>Hola {{recipient_name}},</p><p>{{carrier_name}} notificó <b>{{incidence_label}}</b> en un intento de entrega de la guía <b>{{tracking_id}}</b>. Intentamos contactar al destinatario en el número documentado sin éxito.</p><p>De tu apoyo con un número telefónico alterno para validar dirección y solicitar referencias. <b>De no compartir información en tiempo y forma, el paquete puede ser retornado a origen.</b></p><p>— {{operator_name}}</p>",
    text_body: "Solicitamos número alterno del destinatario para la guía {{tracking_id}} ({{incidence_label}}). De no recibir respuesta, el paquete puede ser retornado a origen.",
  },
  incident_refused_confirmed: {
    subject: "[Incidencia] Rechazo confirmado — {{tracking_id}}",
    html_body: "<p>Hola {{recipient_name}},</p><p>Te comento acerca de la guía <b>{{tracking_id}}</b>. Validamos directamente con el destinatario y <b>afirmó el rechazo</b> del paquete. {{message}}</p><p>De tu apoyo con instrucciones para el envío. Saludos!</p>",
    text_body: "El destinatario confirmó el rechazo de la guía {{tracking_id}}. Necesitamos instrucciones.",
  },
  incident_refused_not_confirmed: {
    subject: "[Incidencia] Rechazo no confirmado — {{tracking_id}}",
    html_body: "<p>Hola {{recipient_name}},</p><p>{{carrier_name}} notificó rechazo de la guía <b>{{tracking_id}}</b>, pero el destinatario indicó que <b>NO rechazó</b> el paquete. Compartió referencias para coordinar un nuevo intento de entrega.</p><p>— {{operator_name}}</p>",
    text_body: "El destinatario indica que no rechazó la guía {{tracking_id}}. Se coordina nuevo intento.",
  },
  incident_refused_no_contact: {
    subject: "[Incidencia] Rechazo — solicitamos apoyo {{tracking_id}}",
    html_body: "<p>Hola {{recipient_name}},</p><p>{{carrier_name}} notificó rechazo de la guía <b>{{tracking_id}}</b>. Intentamos contactar al destinatario sin éxito.</p><p>De tu apoyo con un número alterno para validar información. <b>De no recibir respuesta, el paquete puede ser retornado a origen.</b></p>",
    text_body: "Solicitamos número alterno del destinatario para validar rechazo de {{tracking_id}}.",
  },
  incident_recipient_absent_contacted: {
    subject: "[Incidencia] Destinatario ausente — re-entrega gestionada {{tracking_id}}",
    html_body: "<p>Hola {{recipient_name}},</p><p>Te comento acerca de la guía <b>{{tracking_id}}</b>. {{carrier_name}} notificó <b>{{incidence_label}}</b>. Contactamos al destinatario, se validaron datos y se solicitaron referencias para un nuevo intento de entrega en 24-48hs hábiles.</p><p>— {{operator_name}}</p>",
    text_body: "Coordinamos nuevo intento de entrega de {{tracking_id}} en 24-48hs hábiles.",
  },
  incident_recipient_absent_no_contact: {
    subject: "[Incidencia] Destinatario ausente — apoyo requerido {{tracking_id}}",
    html_body: "<p>Hola {{recipient_name}},</p><p>{{carrier_name}} notificó <b>{{incidence_label}}</b> en la guía <b>{{tracking_id}}</b>. No fue posible contactar al destinatario.</p><p>De tu apoyo con un teléfono alterno o referencias adicionales. De no recibir información, el paquete puede ser retornado a origen.</p>",
    text_body: "No localizamos al destinatario de {{tracking_id}}. Solicitamos número alterno.",
  },
  final_return_to_origin: {
    subject: "[Aviso final] Retorno a origen — {{tracking_id}}",
    html_body: "<p>Hola {{recipient_name}},</p><p>Dando seguimiento a la guía <b>{{tracking_id}}</b>. {{carrier_name}} reporta los intentos de entrega pactados sin éxito y sin respuesta de tu parte a nuestras 3 notificaciones previas.</p><p><b>Por proceso, el paquete será retornado a origen.</b> Lamento los inconvenientes presentados.</p><p>Saludos!</p>",
    text_body: "Tras 3 notificaciones sin respuesta, la guía {{tracking_id}} entra en proceso de devolución a origen.",
  },
};

export default function AdminEmailTemplates() {
  const [keys, setKeys] = useState([]);
  const [variables, setVariables] = useState({});
  const [overrides, setOverrides] = useState({});
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState({ subject: "", html_body: "", text_body: "" });
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setBusy(true);
    try {
      const r = await api.get("/admin/email-templates");
      const body = r.data?.data || {};
      setKeys(body.supported_keys || []);
      setVariables(body.variables || {});
      const map = {};
      (body.items || []).forEach((it) => { map[it.key] = it; });
      setOverrides(map);
      if (!selected && body.supported_keys?.length) {
        chooseKey(body.supported_keys[0], map);
      }
    } catch (e) {
      toast.error("No se pudieron cargar las plantillas");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const chooseKey = (key, overridesArg) => {
    setSelected(key);
    const map = overridesArg || overrides;
    const existing = map[key];
    const fallback = DEFAULT_TEMPLATES[key];
    setForm({
      subject: existing?.subject || fallback?.subject || "",
      html_body: existing?.html_body || fallback?.html_body || "",
      text_body: existing?.text_body || fallback?.text_body || "",
    });
    setPreview(null);
  };

  const onSave = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      await api.put("/admin/email-templates", {
        key: selected, ...form,
      });
      toast.success("Plantilla guardada");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.errors?.[0]?.message || "Error al guardar");
    } finally {
      setBusy(false);
    }
  };

  const onPreview = async () => {
    setBusy(true);
    try {
      const r = await api.post("/admin/email-templates/preview", {
        ...form,
        ctx: {
          recipient_name: "Ana Pérez (responsable)",
          ticket_id: "ab12cd34",
          tracking_id: "FX-123456789",
          carrier_name: "FedEx",
          incidence_label: "Destinatario ausente",
          operator_name: "Juan Pérez",
          client_name: "Cliente Demo",
          message: "Información validada con el destinatario.",
          cta_url: "https://app.myexcellence.com/agente/ab12cd34",
          cta_label: "Ver ticket",
          tenant_name: "MyExcellence",
        },
      });
      setPreview(r.data?.data);
    } catch (e) {
      toast.error("Error al renderizar preview");
    } finally {
      setBusy(false);
    }
  };

  const onResetDefault = () => {
    const fallback = DEFAULT_TEMPLATES[selected];
    if (fallback) {
      setForm({ ...fallback });
      toast.info("Plantilla restaurada al default. Guarda para aplicar.");
    }
  };

  const onDelete = async () => {
    if (!selected || !overrides[selected]) return;
    if (!confirm("¿Eliminar override del tenant? La plantilla volverá al default del sistema.")) return;
    setBusy(true);
    try {
      await api.delete(`/admin/email-templates/${selected}`);
      toast.success("Override eliminado");
      await load();
    } catch (e) {
      toast.error("Error al eliminar");
    } finally {
      setBusy(false);
    }
  };

  const varList = useMemo(() => variables[selected] || [], [variables, selected]);
  const hasOverride = !!overrides[selected];

  return (
    <div className="min-h-screen bg-mye-app">
      <div className="max-w-6xl mx-auto p-6 space-y-4">
        <SaaSHierarchyBreadcrumb />
        <header className="flex items-center gap-3">
          <div className="rounded-lg bg-mye-accent/10 p-2"><Mail className="h-5 w-5 text-mye-accent" /></div>
          <div>
            <h1 className="text-xl font-semibold">Plantillas de correo</h1>
            <p className="text-sm text-mye-ink-muted">
              Edita el contenido de los emails automáticos por tipo de incidente.
              Si no hay override, se usa la plantilla del sistema.
            </p>
          </div>
        </header>

        <div className="grid grid-cols-12 gap-4">
          {/* Sidebar — list of keys */}
          <aside className="col-span-3 rounded-xl border border-mye-stroke bg-white p-3 h-fit">
            <h3 className="text-xs font-medium text-mye-ink-muted uppercase tracking-wide mb-2">
              Plantillas
            </h3>
            <ul className="space-y-1" data-testid="template-key-list">
              {keys.map((k) => (
                <li key={k}>
                  <button
                    onClick={() => chooseKey(k)}
                    data-testid={`template-key-${k}`}
                    className={`w-full text-left px-2.5 py-1.5 rounded-md text-sm transition ${
                      selected === k
                        ? "bg-mye-accent text-white"
                        : "hover:bg-mye-app text-mye-ink"
                    }`}
                  >
                    <span className="flex items-center justify-between gap-2">
                      <span className="truncate">{KEY_LABELS[k] || k}</span>
                      {overrides[k] && (
                        <span className="text-[10px] uppercase opacity-70">custom</span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          {/* Editor */}
          <main className="col-span-9 space-y-4">
            {selected && (
              <>
                <div className="rounded-xl border border-mye-stroke bg-white p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <h2 className="font-medium" data-testid="template-current-name">
                      {KEY_LABELS[selected] || selected}
                    </h2>
                    <div className="flex gap-2">
                      <button onClick={onResetDefault} disabled={busy}
                              data-testid="template-reset-default"
                              className="text-xs px-3 py-1.5 rounded-md border border-mye-stroke hover:bg-mye-app flex items-center gap-1">
                        <RotateCcw className="h-3 w-3" /> Default
                      </button>
                      {hasOverride && (
                        <button onClick={onDelete} disabled={busy}
                                data-testid="template-delete"
                                className="text-xs px-3 py-1.5 rounded-md border border-mye-danger/40 text-mye-danger hover:bg-mye-danger/5 flex items-center gap-1">
                          <Trash2 className="h-3 w-3" /> Borrar override
                        </button>
                      )}
                    </div>
                  </div>

                  <label className="block">
                    <span className="text-xs font-medium text-mye-ink-muted">Asunto</span>
                    <input type="text" value={form.subject}
                           onChange={(e) => setForm({ ...form, subject: e.target.value })}
                           data-testid="template-subject-input"
                           className="mt-1 w-full rounded-md border border-mye-stroke px-3 py-2 text-sm" />
                  </label>

                  <label className="block">
                    <span className="text-xs font-medium text-mye-ink-muted">HTML body</span>
                    <textarea value={form.html_body} rows={8}
                              onChange={(e) => setForm({ ...form, html_body: e.target.value })}
                              data-testid="template-html-input"
                              className="mt-1 w-full rounded-md border border-mye-stroke px-3 py-2 font-mono text-xs" />
                  </label>

                  <label className="block">
                    <span className="text-xs font-medium text-mye-ink-muted">Text body (plain)</span>
                    <textarea value={form.text_body} rows={3}
                              onChange={(e) => setForm({ ...form, text_body: e.target.value })}
                              data-testid="template-text-input"
                              className="mt-1 w-full rounded-md border border-mye-stroke px-3 py-2 font-mono text-xs" />
                  </label>

                  <div className="flex items-center justify-between gap-3 pt-2 border-t border-mye-stroke">
                    <div className="text-xs text-mye-ink-muted">
                      <b>Variables:</b>{" "}
                      {varList.map((v) => (
                        <code key={v} className="bg-mye-app px-1.5 py-0.5 rounded text-[10px] mr-1">
                          {`{{${v}}}`}
                        </code>
                      ))}
                    </div>
                    <div className="flex gap-2">
                      <button onClick={onPreview} disabled={busy}
                              data-testid="template-preview-btn"
                              className="text-sm px-3 py-1.5 rounded-md border border-mye-stroke hover:bg-mye-app flex items-center gap-1">
                        <Eye className="h-4 w-4" /> Preview
                      </button>
                      <button onClick={onSave} disabled={busy}
                              data-testid="template-save-btn"
                              className="text-sm px-4 py-1.5 rounded-md bg-mye-accent text-white hover:bg-mye-accent/90 flex items-center gap-1">
                        <Save className="h-4 w-4" /> Guardar
                      </button>
                    </div>
                  </div>
                </div>

                {preview && (
                  <div className="rounded-xl border border-mye-stroke bg-white p-4 space-y-2"
                       data-testid="template-preview-box">
                    <h3 className="text-xs font-medium text-mye-ink-muted uppercase">Preview</h3>
                    <div className="text-sm"><b>Asunto:</b> {preview.subject}</div>
                    <div className="border border-mye-stroke rounded-md p-3 bg-mye-app/30">
                      <div dangerouslySetInnerHTML={{ __html: preview.html }} />
                    </div>
                    <details>
                      <summary className="text-xs cursor-pointer text-mye-ink-muted">Texto plano</summary>
                      <pre className="text-xs whitespace-pre-wrap mt-1">{preview.text}</pre>
                    </details>
                  </div>
                )}
              </>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
