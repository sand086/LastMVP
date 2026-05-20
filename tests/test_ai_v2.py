"""PROMPT 26 V2 — Tests del módulo Configuración IA.

Cubre P0.12 / P0.13 / P0.14:
  P0.12 PIIMaskingTest — masking determinístico + unmasking selectivo
  P0.13 AICostCapTest  — tope automático bloquea antes de llamar al proveedor
  P0.14 AIOptOutTest   — opt-out bloquea invocaciones futuras
  R38   AIGatewaySingleEntry — sin imports LLM fuera de services/ai/
"""
from __future__ import annotations
import pathlib
import re
import pytest
from httpx import ASGITransport, AsyncClient

from server import app
from core.security import create_access_token
from core.uuid import new_id
from repositories.ai import (
    AIBracketRepository, AIClientConfigRepository,
    AIConsumptionRepository, AIFeatureRepository,
    AIInvocationLogRepository, ensure_ai_indexes,
)
from seeds.ai_catalog import run as seed_ai
from services.ai import gateway as ai_gateway
from services.ai.pii_masker import (
    detect_unknown_tokens, mask, mask_dict, unmask,
)


def _bearer(*, user_id, tenant_id, role="agent"):
    return {"Authorization": f"Bearer {create_access_token(user_id=user_id, tenant_id=tenant_id, role=role, email='u@t')}"}


@pytest.fixture
async def http_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def ai_setup(db):
    """Tenant + cliente + bracket + features sembradas + opt-in completo."""
    await ensure_ai_indexes()
    await seed_ai()
    tid = new_id()
    uid_agent, uid_admin = new_id(), new_id()
    cl_id = new_id()
    await db.tenants.insert_one({"id": tid, "slug": "ai", "name": "AI", "status": "active"})
    await db.users.insert_many([
        {"id": uid_agent, "tenant_id": tid, "email": "a@ai", "role": "agent", "status": "active"},
        {"id": uid_admin, "tenant_id": tid, "email": "ad@ai", "role": "admin", "status": "active"},
    ])
    await db.clients.insert_one({
        "id": cl_id, "tenant_id": tid, "name": "Cliente AI",
        "preferred_channel": "email",
    })
    return {
        "tenant_id": tid,
        "client_id": cl_id,
        "agent_id": uid_agent,
        "admin_id": uid_admin,
    }


# ═══════════════════════════ P0.12 — PIIMaskingTest ══════════════════════
class TestPIIMasking:
    def test_email_phone_address_basic(self):
        text = "Contactar a Pedro Lara, tel +5215512345678, correo pedro@example.com, en Av. Reforma 123 Col. Centro."
        masked, mapping = mask(text, known_names=["Pedro Lara"])
        # No debe quedar el email ni el teléfono ni el nombre
        assert "pedro@example.com" not in masked
        assert "+5215512345678" not in masked
        assert "Pedro Lara" not in masked
        assert "Reforma 123" not in masked
        # Tokens estructurados aparecen
        assert "<EMAIL_" in masked
        assert "<PHONE_" in masked
        assert "<PER_" in masked
        assert "<ADDR_" in masked
        # Mapping permite recuperar
        assert "pedro@example.com" in mapping.values()

    def test_deterministic_same_entity_same_token(self):
        text = "Pedro Lara llamó. Más tarde, Pedro Lara confirmó. Pedro Lara firmó."
        masked, mapping = mask(text, known_names=["Pedro Lara"])
        # 3 ocurrencias del mismo nombre → MISMO token
        assert masked.count("<PER_1>") == 3
        # Mapping tiene UNA sola entrada para el nombre
        per_tokens = [k for k, v in mapping.items() if v == "Pedro Lara"]
        assert len(per_tokens) == 1

    def test_two_distinct_entities_distinct_tokens(self):
        text = "Pedro Lara y Maria Lopez son los responsables."
        masked, mapping = mask(text, known_names=["Pedro Lara", "Maria Lopez"])
        # Dos tokens distintos
        assert "<PER_1>" in masked
        assert "<PER_2>" in masked
        assert mapping["<PER_1>"] != mapping["<PER_2>"]

    def test_unmask_restores_internal(self):
        text = "Avísale a Pedro Lara que su pedido está listo."
        masked, mapping = mask(text, known_names=["Pedro Lara"])
        # Modelo responde con token
        model_response = "Hola <PER_1>, tu pedido está en camino."
        unmasked = unmask(model_response, mapping)
        assert "Pedro Lara" in unmasked
        assert "<PER_1>" not in unmasked

    def test_unknown_token_in_output_is_left_literal(self):
        masked, mapping = mask("Hola Pedro Lara.", known_names=["Pedro Lara"])
        # Modelo aluciona con <PER_99>
        model_response = "Hola <PER_99>, gracias."
        unknown = detect_unknown_tokens(model_response, mapping)
        assert "<PER_99>" in unknown
        # unmask deja el token literal
        out = unmask(model_response, mapping)
        assert "<PER_99>" in out

    def test_no_pii_returns_original(self):
        text = "El paquete fue entregado en buen estado."
        masked, mapping = mask(text)
        assert masked == text
        assert mapping == {}

    def test_mask_dict_harvests_known_fields(self):
        payload = {
            "destinatario": "Pedro Lara",
            "ticket_history": [
                "Llamó Pedro Lara para reportar",
                "Se envió correo a pedro@ex.com",
            ],
            "telefono_cliente": "+52 55 1234 5678",
        }
        masked, mapping = mask_dict(payload)
        # Pedro Lara sustituido en el array history
        assert "Pedro Lara" not in str(masked)
        assert "pedro@ex.com" not in str(masked)
        assert "+52 55 1234 5678" not in str(masked)

    def test_rfc_curp_detected(self):
        text = "RFC del cliente: VECJ880326XXX. CURP: VECJ880326HDFLNN09."
        masked, mapping = mask(text)
        assert "<RFC_" in masked
        assert "VECJ880326XXX" not in masked
        assert any("VECJ880326HDFLNN09" in v or "VECJ880326XXX" in v for v in mapping.values())


# ═══════════════════════════ P0.13 — AICostCapTest ═══════════════════════
class TestAICostCap:
    async def test_consumption_below_cap_invoke_proceeds(self, monkeypatch, ai_setup, db):
        """Cliente bajo el cap → invoke() llega a llamar al proveedor (mock)."""
        # Setup: opt-in, bracket starter ($5 cap), feature classify_motivo
        bracket = await AIBracketRepository().by_name("starter")
        feat = await AIFeatureRepository().by_code("classify_motivo")
        cfg_repo = AIClientConfigRepository(tenant_id=ai_setup["tenant_id"])
        await cfg_repo.upsert({
            "client_id": ai_setup["client_id"],
            "bracket_id": bracket["id"],
            "enabled_features": ["classify_motivo"],
            "is_active": True,
            "opt_in_signature": "Test, 2026-05-09T00:00:00Z",
        })

        # Mockear _call_provider para no gastar API
        called = {"hit": False}
        async def fake_call(*args, **kwargs):
            called["hit"] = True
            return {"text": "DAÑO_PAQUETE", "input_tokens": 100,
                    "output_tokens": 10, "latency_ms": 200}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)

        # Forzar EMERGENT_LLM_KEY
        monkeypatch.setenv("EMERGENT_LLM_KEY", "test-key")

        result = await ai_gateway.invoke(
            tenant_id=ai_setup["tenant_id"], client_id=ai_setup["client_id"],
            user_id=ai_setup["agent_id"], feature_code="classify_motivo",
            raw_input={"description": "Caja rota"},
        )
        assert result.ok, f"Expected ok, got {result.code}: {result.message}"
        assert called["hit"], "Provider must be called when under cap"
        # Log creado
        log_repo = AIInvocationLogRepository(tenant_id=ai_setup["tenant_id"])
        logs = await log_repo.query({"client_id": ai_setup["client_id"]}, limit=10)
        assert any(l["status"] == "success" for l in logs)

    async def test_consumption_at_cap_returns_capped(self, monkeypatch, ai_setup, db):
        """Cliente exactamente al cap → AI_BUDGET_CAPPED, NO llama al proveedor."""
        bracket = await AIBracketRepository().by_name("starter")
        feat = await AIFeatureRepository().by_code("classify_motivo")
        cfg_repo = AIClientConfigRepository(tenant_id=ai_setup["tenant_id"])
        await cfg_repo.upsert({
            "client_id": ai_setup["client_id"],
            "bracket_id": bracket["id"],
            "enabled_features": ["classify_motivo"],
            "is_active": True,
            "opt_in_signature": "Test",
        })
        # Pre-cargar consumo igual al cap
        cons_repo = AIConsumptionRepository(tenant_id=ai_setup["tenant_id"])
        await cons_repo.add_consumption(
            ai_setup["client_id"], input_tokens=100_000, output_tokens=10_000,
            cost_usd=bracket["hard_cap_usd_per_month"],
        )

        called = {"hit": False}
        async def fake_call(*args, **kwargs):
            called["hit"] = True
            return {"text": "x", "input_tokens": 1, "output_tokens": 1, "latency_ms": 1}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)

        result = await ai_gateway.invoke(
            tenant_id=ai_setup["tenant_id"], client_id=ai_setup["client_id"],
            user_id=ai_setup["agent_id"], feature_code="classify_motivo",
            raw_input={"description": "Test"},
        )
        assert not result.ok
        assert result.code == "AI_BUDGET_CAPPED"
        assert result.http_status == 429
        assert called["hit"] is False, "Provider must NOT be called when capped (R40)"

    async def test_estimation_exceeds_cap_blocks_pre_call(self, monkeypatch, ai_setup, db):
        """99% de cap + estimación que rebasa → bloquea ANTES de llamar."""
        bracket = await AIBracketRepository().by_name("starter")
        await AIClientConfigRepository(tenant_id=ai_setup["tenant_id"]).upsert({
            "client_id": ai_setup["client_id"],
            "bracket_id": bracket["id"],
            "enabled_features": ["summarize_timeline"],   # avg_cost_usd=0.0066
            "is_active": True,
            "opt_in_signature": "Test",
        })
        # Setear consumo a 99.9% del cap ($4.995 de $5)
        await AIConsumptionRepository(tenant_id=ai_setup["tenant_id"]).add_consumption(
            ai_setup["client_id"], input_tokens=10, output_tokens=10, cost_usd=4.999,
        )
        called = {"hit": False}
        async def fake_call(*args, **kwargs):
            called["hit"] = True
            return {"text": "x", "input_tokens": 1, "output_tokens": 1, "latency_ms": 1}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)

        result = await ai_gateway.invoke(
            tenant_id=ai_setup["tenant_id"], client_id=ai_setup["client_id"],
            user_id=None, feature_code="summarize_timeline",
            raw_input={"events": ["e1", "e2"]},
        )
        assert not result.ok
        assert result.code == "AI_BUDGET_CAPPED"
        assert called["hit"] is False


# ═══════════════════════════ P0.14 — AIOptOutTest ════════════════════════
class TestAIOptOut:
    async def test_active_client_invokes_then_optout_blocks(self, monkeypatch, ai_setup, db):
        bracket = await AIBracketRepository().by_name("starter")
        cfg_repo = AIClientConfigRepository(tenant_id=ai_setup["tenant_id"])
        await cfg_repo.upsert({
            "client_id": ai_setup["client_id"],
            "bracket_id": bracket["id"],
            "enabled_features": ["classify_motivo"],
            "is_active": True,
            "opt_in_signature": "Test",
        })
        async def fake_call(*args, **kwargs):
            return {"text": "EXTRAVIO", "input_tokens": 100, "output_tokens": 10, "latency_ms": 100}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)
        monkeypatch.setenv("EMERGENT_LLM_KEY", "test-key")

        # 1) Antes del opt-out: invoke pasa
        r1 = await ai_gateway.invoke(
            tenant_id=ai_setup["tenant_id"], client_id=ai_setup["client_id"],
            user_id=ai_setup["agent_id"], feature_code="classify_motivo",
            raw_input={"description": "Paquete extraviado"},
        )
        assert r1.ok, f"Expected ok before opt-out, got {r1.code}"

        # 2) Opt-out
        ok = await cfg_repo.opt_out(ai_setup["client_id"], "Test reason")
        assert ok

        # 3) Después: AI_DISABLED
        r2 = await ai_gateway.invoke(
            tenant_id=ai_setup["tenant_id"], client_id=ai_setup["client_id"],
            user_id=ai_setup["agent_id"], feature_code="classify_motivo",
            raw_input={"description": "Otro caso"},
        )
        assert not r2.ok
        assert r2.code == "AI_DISABLED"
        assert r2.http_status == 403

    async def test_optout_endpoint_writes_log(self, ai_setup, db, http_client):
        """PATCH /api/admin/ai/client-config/{id}/opt-out crea registro en invocation_log."""
        bracket = await AIBracketRepository().by_name("starter")
        await AIClientConfigRepository(tenant_id=ai_setup["tenant_id"]).upsert({
            "client_id": ai_setup["client_id"],
            "bracket_id": bracket["id"],
            "enabled_features": [],
            "is_active": True,
            "opt_in_signature": "Test",
        })
        headers = _bearer(user_id=ai_setup["admin_id"],
                          tenant_id=ai_setup["tenant_id"], role="admin")
        r = await http_client.patch(
            f"/api/admin/ai/client-config/{ai_setup['client_id']}/opt-out",
            json={"reason": "Decisión de privacidad"}, headers=headers,
        )
        assert r.status_code == 200
        # Confirma config desactivada
        cfg = await AIClientConfigRepository(
            tenant_id=ai_setup["tenant_id"]
        ).get(ai_setup["client_id"])
        assert cfg["is_active"] is False
        assert cfg["opt_out_reason"] == "Decisión de privacidad"
        # Log generado
        log_repo = AIInvocationLogRepository(tenant_id=ai_setup["tenant_id"])
        logs = await log_repo.query({"client_id": ai_setup["client_id"]}, limit=10)
        assert any(l["status"] == "opt_out_executed" for l in logs)


# ═════════════════ R39 — Opt-in explícito (validación) ═══════════════════
class TestAIOptInExplicit:
    async def test_invoke_blocked_without_opt_in(self, ai_setup, monkeypatch):
        # No upserteamos config — invoke debe retornar AI_DISABLED
        called = {"hit": False}
        async def fake_call(*args, **kwargs):
            called["hit"] = True
            return {"text": "x", "input_tokens": 1, "output_tokens": 1, "latency_ms": 1}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)

        result = await ai_gateway.invoke(
            tenant_id=ai_setup["tenant_id"], client_id=ai_setup["client_id"],
            user_id=None, feature_code="classify_motivo",
            raw_input={"description": "Test"},
        )
        assert not result.ok
        assert result.code == "AI_DISABLED"
        assert called["hit"] is False

    async def test_invoke_blocked_when_feature_not_enabled(self, ai_setup, monkeypatch):
        bracket = await AIBracketRepository().by_name("starter")
        await AIClientConfigRepository(tenant_id=ai_setup["tenant_id"]).upsert({
            "client_id": ai_setup["client_id"],
            "bracket_id": bracket["id"],
            "enabled_features": ["summarize_timeline"],   # NO classify_motivo
            "is_active": True,
            "opt_in_signature": "T",
        })
        called = {"hit": False}
        async def fake_call(*args, **kwargs):
            called["hit"] = True
            return {"text": "x", "input_tokens": 1, "output_tokens": 1, "latency_ms": 1}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)

        result = await ai_gateway.invoke(
            tenant_id=ai_setup["tenant_id"], client_id=ai_setup["client_id"],
            user_id=None, feature_code="classify_motivo",   # NOT enabled
            raw_input={"description": "x"},
        )
        assert not result.ok
        assert result.code == "AI_DISABLED"
        assert called["hit"] is False


# ═════════════════ R42 — destinatario client_final → draft=true ══════════
class TestR42Draft:
    async def test_client_final_feature_returns_draft_true(self, monkeypatch, ai_setup):
        bracket = await AIBracketRepository().by_name("scale")
        await AIClientConfigRepository(tenant_id=ai_setup["tenant_id"]).upsert({
            "client_id": ai_setup["client_id"],
            "bracket_id": bracket["id"],
            "enabled_features": ["draft_response_to_client"],
            "is_active": True,
            "opt_in_signature": "T",
        })
        async def fake_call(*args, **kwargs):
            return {"text": "Estimado <PER_1>, lamentamos el inconveniente.",
                    "input_tokens": 200, "output_tokens": 30, "latency_ms": 200}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)
        monkeypatch.setenv("EMERGENT_LLM_KEY", "test-key")

        result = await ai_gateway.invoke(
            tenant_id=ai_setup["tenant_id"], client_id=ai_setup["client_id"],
            user_id=ai_setup["agent_id"], feature_code="draft_response_to_client",
            raw_input={"context": "Ticket de Pedro Lara",
                       "destinatario": "Pedro Lara", "tone": "empathetic"},
        )
        assert result.ok, result.code
        assert result.data["draft"] is True   # R42

    async def test_agent_internal_feature_returns_draft_false(self, monkeypatch, ai_setup):
        bracket = await AIBracketRepository().by_name("starter")
        await AIClientConfigRepository(tenant_id=ai_setup["tenant_id"]).upsert({
            "client_id": ai_setup["client_id"],
            "bracket_id": bracket["id"],
            "enabled_features": ["classify_motivo"],
            "is_active": True,
            "opt_in_signature": "T",
        })
        async def fake_call(*args, **kwargs):
            return {"text": "EXTRAVIO", "input_tokens": 100,
                    "output_tokens": 5, "latency_ms": 100}
        monkeypatch.setattr(ai_gateway, "_call_provider", fake_call)
        monkeypatch.setenv("EMERGENT_LLM_KEY", "test-key")

        result = await ai_gateway.invoke(
            tenant_id=ai_setup["tenant_id"], client_id=ai_setup["client_id"],
            user_id=ai_setup["agent_id"], feature_code="classify_motivo",
            raw_input={"description": "El paquete nunca llegó"},
        )
        assert result.ok
        assert result.data["draft"] is False



# ═════════════════ R38 — AIGateway single entry point ═══════════════════
class TestR38SingleEntry:
    def test_no_llm_imports_outside_services_ai(self):
        """R38 — ningún archivo del backend (excepto services/ai/) debe importar
        anthropic, openai o emergentintegrations.llm directamente."""
        backend = pathlib.Path("/app/backend")
        forbidden = re.compile(
            r"^\s*(?:from|import)\s+(?:anthropic|openai|emergentintegrations\.llm)",
            re.MULTILINE,
        )
        offenders = []
        for path in backend.rglob("*.py"):
            # Permitidos: archivos dentro de services/ai/
            if "services/ai/" in str(path):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if forbidden.search(text):
                offenders.append(str(path.relative_to(backend)))
        assert not offenders, (
            "R38 violado — los siguientes archivos importan SDKs LLM fuera de "
            f"services/ai/: {offenders}"
        )
