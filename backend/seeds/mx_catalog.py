"""Catálogo estándar mexicano — 12 motivos + 18 soluciones.

Usado por el wizard de onboarding (Bundle E paso 5) cuando el admin elige
"Cargar catálogo estándar mexicano".

Los motivos y soluciones reflejan operaciones reales de logística MX
(reclamos, reagendados, dirección insuficiente, etc.). El admin puede
editarlos luego desde /admin/catalogo.

Función `seed_for_tenant` idempotente: si el motivo o solución ya existe
(por `code` o `name`+`motivo_id`), no duplica.
"""
from __future__ import annotations

from repositories.catalog import MotivoRepository, SolucionRepository


# ---- 12 Motivos estándar ----
# `restricted=True` para motivos sensibles que NO admiten automatización
# (matriz de permisos los bloquea con tooltip).
STANDARD_MX_MOTIVOS: list[dict] = [
    {"code": "DIR_INSUF", "name": "Dirección insuficiente", "restricted": False},
    {"code": "DESTI_AUS", "name": "Destinatario ausente", "restricted": False},
    {"code": "RECHAZO_DEST", "name": "Rechazo del destinatario", "restricted": False},
    {"code": "DIR_EQUIV", "name": "Dirección equivocada / mudanza", "restricted": False},
    {"code": "DANO_TRANSITO", "name": "Daño en tránsito", "restricted": False},
    {"code": "PERDIDA", "name": "Pérdida o robo", "restricted": True},  # legal/aseguradora
    {"code": "REAGENDA_CLI", "name": "Reagendado por cliente", "restricted": False},
    {"code": "FALTANTE", "name": "Mercancía faltante (incompleta)", "restricted": False},
    {"code": "EQUIVOCA", "name": "Mercancía equivocada", "restricted": False},
    {"code": "AUTORIDAD", "name": "Acceso restringido por autoridad", "restricted": True},
    {"code": "CARRIER_DELAY", "name": "Retraso del carrier", "restricted": False},
    {"code": "CANCEL_PEDIDO", "name": "Cancelación de pedido", "restricted": False},
]


# ---- 18 Soluciones estándar ----
# Mapeadas a uno o más motivos via `motivo_codes`. La función seed las inserta
# una vez por motivo asociado (R03 — matriz motivo×canal queda inicial en
# manual).
STANDARD_MX_SOLUCIONES: list[dict] = [
    {"name": "Validar dirección con destinatario", "motivo_codes": ["DIR_INSUF", "DIR_EQUIV"], "automatable": True},
    {"name": "Reagendar entrega", "motivo_codes": ["DESTI_AUS", "REAGENDA_CLI", "CARRIER_DELAY"], "automatable": True},
    {"name": "Devolver a origen", "motivo_codes": ["RECHAZO_DEST", "DIR_EQUIV"], "automatable": False},
    {"name": "Solicitar reposición o reembolso", "motivo_codes": ["DANO_TRANSITO", "PERDIDA", "FALTANTE"], "automatable": False},
    {"name": "Levantar reclamo a carrier", "motivo_codes": ["DANO_TRANSITO", "PERDIDA", "CARRIER_DELAY"], "automatable": False},
    {"name": "Cambiar dirección de entrega", "motivo_codes": ["DIR_INSUF", "DIR_EQUIV"], "automatable": True},
    {"name": "Coordinar punto de retiro", "motivo_codes": ["DESTI_AUS", "RECHAZO_DEST"], "automatable": True},
    {"name": "Reenviar mercancía faltante", "motivo_codes": ["FALTANTE"], "automatable": False},
    {"name": "Reemplazar mercancía dañada", "motivo_codes": ["DANO_TRANSITO", "EQUIVOCA"], "automatable": False},
    {"name": "Reembolsar al cliente", "motivo_codes": ["PERDIDA", "CANCEL_PEDIDO", "EQUIVOCA"], "automatable": False},
    {"name": "Escalar a supervisor", "motivo_codes": ["AUTORIDAD", "PERDIDA"], "automatable": False},
    {"name": "Notificar al área de CxC del cliente", "motivo_codes": ["PERDIDA", "FALTANTE", "DANO_TRANSITO"], "automatable": True},
    {"name": "Cerrar caso sin acción (mercancía recibida)", "motivo_codes": ["REAGENDA_CLI"], "automatable": False},
    {"name": "Auditar peso o dimensiones", "motivo_codes": ["FALTANTE", "EQUIVOCA"], "automatable": False},
    {"name": "Re-etiquetar guía", "motivo_codes": ["DIR_INSUF", "EQUIVOCA"], "automatable": True},
    {"name": "Coordinar entrega supervisada (autoridad)", "motivo_codes": ["AUTORIDAD"], "automatable": False},
    {"name": "Solicitar evidencia fotográfica", "motivo_codes": ["DANO_TRANSITO", "DESTI_AUS"], "automatable": True},
    {"name": "Iniciar conciliación financiera", "motivo_codes": ["PERDIDA", "DANO_TRANSITO"], "automatable": False},
]


async def seed_for_tenant(tenant_id: str) -> dict:
    """Idempotente. Inserta motivos faltantes y soluciones faltantes.

    Returns:
        dict con counters: { motivos_inserted, motivos_skipped,
                             soluciones_inserted, soluciones_skipped }
    """
    motivo_repo = MotivoRepository(tenant_id=tenant_id)
    sol_repo = SolucionRepository(tenant_id=tenant_id)

    motivos_inserted = 0
    motivos_skipped = 0
    code_to_motivo: dict[str, dict] = {}

    for m in STANDARD_MX_MOTIVOS:
        existing = await motivo_repo.by_code(m["code"])
        if existing:
            motivos_skipped += 1
            code_to_motivo[m["code"]] = existing
            continue
        created = await motivo_repo.create(
            code=m["code"], name=m["name"],
            restricted=m["restricted"], active=True,
        )
        code_to_motivo[m["code"]] = created
        motivos_inserted += 1

    soluciones_inserted = 0
    soluciones_skipped = 0
    for s in STANDARD_MX_SOLUCIONES:
        for code in s["motivo_codes"]:
            motivo = code_to_motivo.get(code)
            if not motivo:
                continue
            existing = await sol_repo.find_one(
                {"motivo_id": motivo["id"], "name": s["name"]},
            )
            if existing:
                soluciones_skipped += 1
                continue
            await sol_repo.create(
                motivo_id=motivo["id"], name=s["name"],
                steps=[], template_email=None, template_wa=None,
                automatable=bool(s.get("automatable", False)),
            )
            soluciones_inserted += 1

    return {
        "motivos_inserted": motivos_inserted,
        "motivos_skipped": motivos_skipped,
        "soluciones_inserted": soluciones_inserted,
        "soluciones_skipped": soluciones_skipped,
    }
