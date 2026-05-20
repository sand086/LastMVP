/**
 * StepTenantInfo — Paso 2 · Datos básicos del tenant (RFC + dirección + tel).
 *
 * Consume `MxInput` (RFC, teléfono) y `MxAddressInput` (CP lookup) — BP-05.
 *
 * Persiste step_data en el doc de onboarding. NO escribe directo en la
 * colección `tenants` desde acá; eso lo hace el wizard al completar
 * vía un endpoint dedicado en /admin/tenants (out of scope para Bundle E,
 * los datos quedan disponibles en el doc de onboarding para que el siguiente
 * agente los lea).
 */
import { useState } from "react";
import { MxInput } from "@/components/MxInput";
import { MxAddressInput } from "@/components/MxAddressInput";
import ONBOARDING_COPY from "../copy";

export function StepTenantInfo({ onAdvance, busy = false, initialData = {} }) {
  const c = ONBOARDING_COPY.steps.step_2_tenant_info;
  const [name, setName] = useState(initialData.name || "");
  const [rfc, setRfc] = useState(initialData.rfc || "");
  const [phone, setPhone] = useState(initialData.phone || "");
  const [address, setAddress] = useState(initialData.address_mx || null);
  const [respectHolidays, setRespectHolidays] = useState(
    initialData.respect_holidays ?? true,
  );

  const canContinue = name.trim().length >= 2;

  function submit() {
    onAdvance({
      name: name.trim(),
      rfc: rfc.trim(),
      phone: phone.trim(),
      address_mx: address,
      respect_holidays: respectHolidays,
    });
  }

  return (
    <div className="space-y-4" data-testid="onboarding-step-tenant-info">
      <div>
        <h2 className="text-base font-semibold text-mye-ink mb-1">{c.title}</h2>
        <p className="text-xs text-mye-ink-muted">{c.subtitle}</p>
      </div>

      <label className="block">
        <span className="block text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-1">
          {c.fields.name}
        </span>
        <input
          type="text" value={name} disabled={busy}
          onChange={(e) => setName(e.target.value)}
          data-testid="onboarding-tenant-name"
          className="w-full rounded-md border border-mye-border px-3 py-2 text-sm"
        />
      </label>

      <MxInput
        type="rfc" label={c.fields.rfc} value={rfc}
        onChange={setRfc} disabled={busy}
        testId="onboarding-tenant-rfc"
      />

      <MxInput
        type="telefono" label={c.fields.phone} value={phone}
        onChange={setPhone} disabled={busy}
        testId="onboarding-tenant-phone"
      />

      <div>
        <div className="text-[10px] uppercase tracking-wider font-mono text-mye-ink-muted mb-2">
          {c.fields.address}
        </div>
        <MxAddressInput
          value={address} onChange={setAddress} disabled={busy}
          testIdPrefix="onboarding-tenant-address"
        />
      </div>

      <label className="flex items-start gap-2 text-xs cursor-pointer">
        <input
          type="checkbox" checked={respectHolidays} disabled={busy}
          onChange={(e) => setRespectHolidays(e.target.checked)}
          data-testid="onboarding-tenant-respect-holidays"
          className="mt-0.5"
        />
        <span>
          <span className="font-medium text-mye-ink">
            {c.fields.respect_holidays}
          </span>
          <span className="block text-mye-ink-muted">
            {c.fields.respect_holidays_help}
          </span>
        </span>
      </label>

      <div className="pt-2">
        <button
          type="button"
          disabled={busy || !canContinue}
          onClick={submit}
          data-testid="onboarding-tenant-info-continue"
          className="w-full rounded-md bg-mye-accent text-white text-sm font-medium py-2 hover:bg-mye-accent-hover disabled:opacity-50"
        >
          {c.cta_primary} →
        </button>
      </div>
    </div>
  );
}

export default StepTenantInfo;
