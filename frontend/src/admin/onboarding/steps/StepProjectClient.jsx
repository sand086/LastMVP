/**
 * StepProjectClient — Paso 3 · Primer proyecto + primer cliente.
 *
 * Combina la creación del proyecto y, opcionalmente, el primer cliente.
 * El payload se persiste en step_data; la creación real en /admin/hierarchy
 * queda fuera de Bundle E (lo hace el operador desde /admin/jerarquia con los
 * datos pre-llenados si quiere).
 */
import { useState } from "react";
import { MxInput } from "@/components/MxInput";
import ONBOARDING_COPY from "../copy";

export function StepProjectClient({ onAdvance, busy = false, initialData = {} }) {
  const c = ONBOARDING_COPY.steps.step_3_project_client;
  const [projectName, setProjectName] = useState(initialData.project_name || "");
  const [projectDesc, setProjectDesc] = useState(initialData.project_description || "");
  const [createClient, setCreateClient] = useState(
    initialData.create_client_now ?? true,
  );
  const [clientName, setClientName] = useState(initialData.client_name || "");
  const [clientRfc, setClientRfc] = useState(initialData.client_rfc || "");
  const [opsContact, setOpsContact] = useState(initialData.ops_contact || "");
  const [cxcEmail, setCxcEmail] = useState(initialData.cxc_email || "");
  const [volumeEstimate, setVolumeEstimate] = useState(initialData.volume || "");

  const canContinue = projectName.trim().length >= 2
    && (!createClient || clientName.trim().length >= 2);

  function submit() {
    onAdvance({
      project_name: projectName.trim(),
      project_description: projectDesc.trim(),
      create_client_now: createClient,
      client_name: createClient ? clientName.trim() : null,
      client_rfc: createClient ? clientRfc.trim() : null,
      ops_contact: createClient ? opsContact.trim() : null,
      cxc_email: createClient ? cxcEmail.trim() : null,
      volume: createClient ? Number(volumeEstimate) || 0 : 0,
    });
  }

  return (
    <div className="space-y-4" data-testid="onboarding-step-project-client">
      <div>
        <h2 className="text-base font-semibold text-mye-ink mb-1">{c.title}</h2>
        <p className="text-xs text-mye-ink-muted">{c.subtitle}</p>
      </div>

      <fieldset className="space-y-3 border border-mye-border rounded-md p-3">
        <legend className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted px-1">
          Proyecto
        </legend>
        <label className="block">
          <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
            {c.project_section.name}
          </span>
          <input
            type="text" value={projectName} disabled={busy}
            placeholder={c.project_section.name_placeholder}
            onChange={(e) => setProjectName(e.target.value)}
            data-testid="onboarding-project-name"
            className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
          />
        </label>
        <label className="block">
          <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
            {c.project_section.description}
          </span>
          <textarea
            rows={2} value={projectDesc} disabled={busy} maxLength={300}
            onChange={(e) => setProjectDesc(e.target.value)}
            data-testid="onboarding-project-description"
            className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
          />
        </label>
      </fieldset>

      <label className="flex items-start gap-2 text-xs cursor-pointer">
        <input
          type="checkbox" checked={createClient} disabled={busy}
          onChange={(e) => setCreateClient(e.target.checked)}
          data-testid="onboarding-toggle-create-client"
          className="mt-0.5"
        />
        <span>
          <span className="font-medium text-mye-ink">{c.client_section.toggle_label}</span>
          <span className="block text-mye-ink-muted">{c.client_section.toggle_help}</span>
        </span>
      </label>

      {createClient && (
        <fieldset className="space-y-3 border border-mye-border rounded-md p-3">
          <legend className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted px-1">
            Primer cliente
          </legend>
          <label className="block">
            <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
              {c.client_section.name}
            </span>
            <input
              type="text" value={clientName} disabled={busy}
              placeholder={c.client_section.name_placeholder}
              onChange={(e) => setClientName(e.target.value)}
              data-testid="onboarding-client-name"
              className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
            />
          </label>
          <MxInput
            type="rfc" label={c.client_section.rfc} value={clientRfc}
            onChange={setClientRfc} disabled={busy}
            testId="onboarding-client-rfc"
          />
          <label className="block">
            <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
              {c.client_section.ops_contact}
            </span>
            <input
              type="email" value={opsContact} disabled={busy}
              onChange={(e) => setOpsContact(e.target.value)}
              placeholder="ops@cliente.com"
              data-testid="onboarding-client-ops-contact"
              className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
            />
          </label>
          <label className="block">
            <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
              {c.client_section.cxc_contact}
            </span>
            <input
              type="email" value={cxcEmail} disabled={busy}
              onChange={(e) => setCxcEmail(e.target.value)}
              placeholder="cxc@cliente.com"
              data-testid="onboarding-client-cxc-email"
              className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
            />
          </label>
          <label className="block">
            <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
              {c.client_section.volume_estimate}
            </span>
            <input
              type="number" min="0" value={volumeEstimate} disabled={busy}
              onChange={(e) => setVolumeEstimate(e.target.value)}
              placeholder="500"
              data-testid="onboarding-client-volume"
              className="w-full rounded-md border border-mye-border px-3 py-2 text-sm font-mono"
            />
          </label>
        </fieldset>
      )}

      <p className="text-xs text-mye-ink-muted italic">{c.info}</p>

      <div className="pt-2">
        <button
          type="button"
          disabled={busy || !canContinue}
          onClick={submit}
          data-testid="onboarding-project-client-continue"
          className="w-full rounded-md bg-mye-accent text-white text-sm font-medium py-2 hover:bg-mye-accent-hover disabled:opacity-50"
        >
          {c.cta_primary} →
        </button>
      </div>
    </div>
  );
}

export default StepProjectClient;
