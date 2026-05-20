/**
 * ONBOARDING_COPY — Bundle E (Iter33).
 *
 * Microcopy centralizado para el wizard de onboarding admin.
 * NO usar strings inline en los step components — todos vienen de acá.
 *
 * Tono y terminología (decisión de Producto):
 *   - Tutea al usuario ("Tú configuras", "Tu tenant").
 *   - Lenguaje claro y directo, sin jergas técnicas.
 *   - Microcopy de errores: cómo arreglar, no qué pasó.
 *   - Localización México (BP-05).
 *
 * Si V4 introduce pt-BR, migrar este archivo a `messages.es-MX.js` +
 * `messages.pt-BR.js` con vue-i18n / react-intl.
 */
export const ONBOARDING_COPY = Object.freeze({
  header: {
    title: "Bienvenido a tu nuevo tenant",
    progress_label: (n, total) => `Paso ${n} de ${total}`,
    estimated_time: (mins) => `≈ ${mins} min`,
    close_button: "Cerrar",
    close_confirm: "¿Cerrar el asistente? Podés continuar después desde el menú.",
    skip_button: "Saltar este paso",
    back_button: "Atrás",
    next_button: "Siguiente",
    finish_button: "Finalizar",
    pre_completed_badge: "Ya configurado por otro admin",
  },

  steps: {
    step_1_welcome: {
      title: "Empecemos por lo básico",
      subtitle: "Vas a configurar tu nuevo tenant en 6 pasos cortos.",
      body: [
        "MyExcellence detecta envíos con problemas (vía webhook, pulling o layout), decide si automatiza o asigna a un humano, y ejecuta — respetando los permisos contratados por cada cliente.",
        "En los siguientes pasos vas a:",
      ],
      checklist: [
        "Capturar datos fiscales y operativos del tenant.",
        "Crear tu primer proyecto y primer cliente.",
        "Configurar al menos un carrier (FedEx, DHL, 99 Minutos, etc.).",
        "Cargar el catálogo de motivos y soluciones (12 + 18 estándar MX).",
        "Definir la matriz de permisos de automatización (R03).",
      ],
      recommendation:
        "Tené a mano los datos fiscales de tu organización y las credenciales que te asignaron los carriers que vas a operar.",
      cta_primary: "Empecemos",
      time_min: 12,
    },

    step_2_tenant_info: {
      title: "Información básica del tenant",
      subtitle: "Datos fiscales y de operación que aparecen en facturación y notificaciones.",
      fields: {
        name: "Nombre comercial",
        rfc: "RFC",
        rfc_help: "RFC con homoclave. Personas morales: XXXX######XXX.",
        address: "Dirección fiscal",
        phone: "Teléfono de contacto",
        business_hours: "Horario laboral default",
        respect_holidays: "Respetar festivos nacionales de México",
        respect_holidays_help: "Las SLA pausan en festivos nacionales (Bundle D · LATAM).",
      },
      cta_primary: "Guardar y continuar",
    },

    step_3_project_client: {
      title: "Primer proyecto y primer cliente",
      subtitle:
        "Un proyecto agrupa clientes que comparten configuración operativa. La mayoría de tenants empieza con uno solo.",
      project_section: {
        name: "Nombre del proyecto",
        name_placeholder: "Operación logística MX",
        description: "Descripción (opcional)",
      },
      client_section: {
        toggle_label: "Crear primer cliente ahora",
        toggle_help:
          "Recomendado. Podés agregar más clientes después desde /admin/jerarquia.",
        name: "Nombre comercial del cliente",
        name_placeholder: "Cubbo",
        rfc: "RFC del cliente",
        ops_contact: "Contacto operativo principal",
        cxc_contact: "Contacto de cuenta x cobrar (para reclamos)",
        volume_estimate: "Volumen mensual estimado de guías",
      },
      info: "Mensaje educativo: podés agregar más clientes después desde el módulo Jerarquía.",
      cta_primary: "Guardar y continuar",
    },

    step_4_carriers: {
      title: "Carriers y credenciales",
      subtitle:
        "Los carriers son las empresas que ejecutan tus envíos. MyExcellence se conecta a sus APIs para rastrearlos. Necesitarás las credenciales que cada uno te asignó.",
      banner_skipped:
        "Carriers pendientes — sin al menos uno, MyE no puede operar sobre envíos reales.",
      states: {
        unconfigured: "Sin configurar",
        platform_managed:
          "MyExcellence gestiona este carrier a nivel plataforma. No requiere credenciales tuyas.",
        pending: "Por configurar",
      },
      cta_primary: "Guardar y continuar",
      cta_skip: "Saltar y configurar después",
    },

    step_5_catalog: {
      title: "Catálogo de motivos y soluciones",
      subtitle:
        "Los motivos son las razones operativas por las que un envío necesita atención. Las soluciones son las acciones que tu equipo puede ejecutar.",
      mandatory_note: "Este paso es obligatorio. Sin catálogo, los agentes no pueden gestionar tickets.",
      cta_primary: "Cargar catálogo estándar mexicano",
      cta_primary_help:
        "Incluye 12 motivos y 18 soluciones de uso común en logística MX. Editás después desde /admin/catalogo.",
      cta_secondary: "Cargar mi propio catálogo (CSV)",
      cta_secondary_help: "Para tenants avanzados con catálogo propio ya definido.",
      success: (m, s) =>
        `${m} motivos y ${s} soluciones cargados. Revisalos en /admin/catalogo.`,
      partial: (skipped) =>
        `Algunos registros ya existían (${skipped}). Solo se agregaron los faltantes.`,
    },

    step_6_automation_matrix: {
      title: "Matriz de permisos de automatización",
      subtitle:
        "Por regla R03, MyExcellence NUNCA ejecuta automatización sin tu autorización. Definí qué combinaciones de motivo + canal pueden ejecutarse sin intervención humana.",
      default_note:
        "Default seguro: TODO en manual. Activá automatización solo donde tu equipo conoce bien el flujo.",
      channels: {
        email: "Email",
        whatsapp: "WhatsApp",
        carrier_api: "API a carrier",
      },
      modes: {
        manual: "Manual",
        automatic: "Automático",
      },
      restricted_tooltip:
        "Motivo restringido por política legal. Solo gestión manual.",
      confirm_activation:
        "Confirmá que tu equipo está capacitado para manejar estas automatizaciones. Las acciones se ejecutan sin intervención humana.",
      cta_primary: "Guardar matriz",
      cta_skip: "Saltar — todo en manual",
    },

    completion: {
      title: "¡Listo! Tu tenant está configurado.",
      subtitle: "Configuración inicial completada exitosamente.",
      summary_lead: "Has configurado:",
      cta_primary: "Ir al Dashboard",
      cta_secondary: "Tomar tour interactivo",
    },
  },

  errors: {
    rfc_invalid: "Capturá un RFC válido (12-13 caracteres con homoclave).",
    cp_invalid: "El código postal debe tener 5 dígitos.",
    phone_invalid: "Capturá un teléfono con código de país (ej. +52).",
    required: (field) => `${field} es obligatorio para continuar.`,
    network: "Error de conexión. Probá de nuevo en unos segundos.",
    catalog_partial:
      "El catálogo se cargó parcialmente. Algunos motivos ya existían en tu tenant.",
  },

  tooltips: {
    rfc: "El RFC del tenant. Personas morales: XXXX######XXX. Personas físicas: XXXX######XXX.",
    cp: "Código postal mexicano de 5 dígitos. Autocompletamos estado y colonia.",
    phone: "Teléfono con código de país. Ej: +525512345678.",
    automation_default:
      "Default seguro: manual. Cambiá a automático solo donde confíes plenamente en el flujo.",
  },
});

export default ONBOARDING_COPY;
