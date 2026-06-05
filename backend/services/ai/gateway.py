"""AIGateway — ÚNICO punto de entrada a proveedores LLM externos (R38).

Reglas que ENFORZA este gateway:
  R36 — Recibe ya texto enmascarado (PIIMasker es responsabilidad del caller).
  R37 — Cada invocación se persiste append-only en ai_invocation_log.
  R39 — is_active=true + bracket asignado + feature en enabled_features.
  R40 — Tope mensual hard_cap_usd_per_month NO se bypasea (sin override runtime).

Si el cliente configuró custom_api_key + custom_provider, se usa ese; si no,
se usa la EMERGENT_LLM_KEY universal.

Costos: estimados por (input_tokens / 1000) * input_rate + (output_tokens / 1000)
        * output_rate. Tabla de tarifas USD por 1k tokens en MODEL_PRICING.
"""
from __future__ import annotations
import hashlib
import os
import time

from core.crypto import decrypt as decrypt_str, encrypt as encrypt_str
from core.logger import log
from core.uuid import new_id
from repositories.ai import (
    AIBracketRepository,
    AIClientConfigRepository,
    AIConsumptionRepository,
    AIFeatureRepository,
    AIInvocationLogRepository,
)
from services.ai.circuit_breaker import breaker
from services.ai.prompt_cache import cache as prompt_cache
from services.ai.pii_masker import detect_unknown_tokens, mask_dict, unmask


# Tarifas USD por 1K tokens (input, output). Fuente: precios públicos Anthropic/OpenAI feb 2026.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-haiku-4-5-20251001": (0.0008, 0.004),
    "claude-sonnet-4-5-20250929": (0.003, 0.015),
    "claude-opus-4-5-20251101": (0.015, 0.075),
    # OpenAI
    "gpt-4.1-mini": (0.0004, 0.0016),
    "gpt-4.1": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.0025, 0.01),
    # Gemini (vía universal key)
    "gemini-2.5-flash": (0.0003, 0.0025),
    "gemini-2.5-pro": (0.00125, 0.01),
}

DEFAULT_USD_TO_MXN = 17.50  # fallback estático; admin puede ajustar

# Códigos de error específicos de IA (no son ErrorCode estándar)
AI_DISABLED = "AI_DISABLED"
AI_BUDGET_CAPPED = "AI_BUDGET_CAPPED"
AI_FEATURE_NOT_FOUND = "AI_FEATURE_NOT_FOUND"
AI_INVALID_INPUT = "AI_INVALID_INPUT"
AI_PROVIDER_UNAVAILABLE = "AI_PROVIDER_UNAVAILABLE"
AI_PROVIDER_TIMEOUT = "AI_PROVIDER_TIMEOUT"


class AIGatewayResult:
    def __init__(self, *, ok: bool, code: str | None = None, message: str | None = None,
                 data: dict | None = None, http_status: int = 200):
        self.ok = ok
        self.code = code
        self.message = message
        self.data = data or {}
        self.http_status = http_status

    def to_dict(self) -> dict:
        return {"ok": self.ok, "code": self.code, "message": self.message,
                "data": self.data, "http_status": self.http_status}


def _hash(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def _estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = MODEL_PRICING.get(model)
    if not rates:
        # fallback razonable
        rates = (0.003, 0.015)
    in_rate, out_rate = rates
    return (input_tokens / 1000.0) * in_rate + (output_tokens / 1000.0) * out_rate


def _resolve_credentials(client_config: dict) -> tuple[str, str]:
    """Devuelve (provider, api_key) con override del cliente si existe."""
    custom_provider = client_config.get("custom_provider")
    enc_key = client_config.get("custom_api_key_encrypted")
    if custom_provider and enc_key:
        try:
            return custom_provider, decrypt_str(enc_key)
        except Exception:
            log.warning("ai_custom_key_decrypt_failed", extra={"context": {
                "client_id": client_config.get("client_id"),
            }})
    universal = os.environ["EMERGENT_LLM_KEY"]
    return "anthropic", universal


def _litellm_model(provider: str, model: str) -> str:
    """Build a LiteLLM model id while preserving already-prefixed ids."""
    if "/" in model:
        return model
    provider = (provider or "").lower()
    if provider in {"anthropic", "openai", "gemini"}:
        return f"{provider}/{model}"
    if provider in {"google", "google-genai", "google_genai"}:
        return f"gemini/{model}"
    return model


async def _call_provider(provider: str, model: str, system: str, prompt: str,
                         api_key: str, *, timeout_s: float = 30.0) -> dict:
    """Llamada real al proveedor vía LiteLLM.

    Devuelve {text, input_tokens, output_tokens, latency_ms}.
    En caso de fallo, lanza excepción con .code (`provider_unavailable`/`timeout`/`error`).
    """
    from litellm import acompletion

    started = time.monotonic()
    try:
        resp = await acompletion(
            model=_litellm_model(provider, model),
            messages=[
                {"role": "system", "content": system or ""},
                {"role": "user", "content": prompt},
            ],
            api_key=api_key,
            timeout=timeout_s,
        )
        text = resp.choices[0].message.content if resp and resp.choices else ""
        if not isinstance(text, str):
            text = str(text)
    except TimeoutError as e:
        raise _GatewayError(AI_PROVIDER_TIMEOUT, str(e)) from e
    except Exception as e:  # noqa: BLE001
        msg = str(e).lower()
        if "401" in msg or "unauthorized" in msg or "invalid api key" in msg:
            raise _GatewayError(AI_PROVIDER_UNAVAILABLE, "Credenciales inválidas") from e
        if "429" in msg or "rate" in msg:
            raise _GatewayError(AI_PROVIDER_UNAVAILABLE, "Rate limit del proveedor") from e
        raise _GatewayError(AI_PROVIDER_UNAVAILABLE, str(e)[:200]) from e

    latency_ms = int((time.monotonic() - started) * 1000)
    # Estimación local de tokens (heurística 4 chars / token).
    input_tokens = max(1, (len(prompt) + len(system or "")) // 4)
    output_tokens = max(1, len(text) // 4)
    return {"text": text, "input_tokens": input_tokens,
            "output_tokens": output_tokens, "latency_ms": latency_ms}


class _GatewayError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# ────────────────── Builders de prompts por feature ──────────────────────
def _build_prompt(feature_code: str, masked_input: dict) -> tuple[str, str]:
    """Devuelve (system_message, user_prompt) según el feature_code.

    Convención: el system_message NUNCA contiene PII (sólo contexto operativo).
    R41 — los prompts NO pueden referenciar atributos discriminatorios.
    """
    if feature_code == "classify_motivo":
        system = (
            "Eres un clasificador de motivos de incidencia para una plataforma "
            "de logística. Recibes la descripción de una incidencia y debes "
            "responder ÚNICAMENTE con uno de estos códigos: DIR_INSUFICIENTE, "
            "DAÑO_PAQUETE, RETRASO, EXTRAVIO, REDIRECCION, OTRO. "
            "No infieras género, código postal, raza ni nacionalidad — solo "
            "razona sobre la naturaleza operativa de la incidencia."
        )
        descr = masked_input.get("description") or masked_input.get("text") or ""
        user = f"Incidencia: {descr}\n\nResponde con el código exacto."

    elif feature_code == "summarize_timeline":
        system = (
            "Eres un asistente operativo para Customer Success. Resume un "
            "timeline de eventos de un ticket en máximo 4 líneas en español, "
            "en tono profesional y neutral. No menciones género, edad, nombres "
            "de personas distintos a los que aparezcan literalmente, ni "
            "atributos demográficos."
        )
        events = masked_input.get("events") or masked_input.get("ticket_history") or []
        if isinstance(events, list):
            joined = "\n".join(f"- {ev}" for ev in events)
        else:
            joined = str(events)
        user = f"Timeline:\n{joined}\n\nResume en máximo 4 líneas."

    elif feature_code == "draft_response_to_client":
        tone = masked_input.get("tone") or "empathetic"
        system = (
            "Eres un asistente que redacta respuestas en español para clientes "
            "finales de paquetería. Tono: " + tone + ". Reglas absolutas:\n"
            "- Reconocer el problema brevemente.\n"
            "- Proponer un siguiente paso claro y accionable.\n"
            "- No prometer plazos que no estén en el contexto.\n"
            "- No usar datos personales fuera de los tokens enmascarados.\n"
            "- No inferir género ni asumir atributos del cliente.\n"
            "Output: SOLO el texto de la respuesta, sin metacomentarios."
        )
        ctx = masked_input.get("context") or masked_input.get("ticket_history") or ""
        if isinstance(ctx, list):
            ctx = "\n".join(f"- {c}" for c in ctx)
        user = f"Contexto del ticket:\n{ctx}\n\nRedacta la respuesta al cliente."

    else:
        # Genérico — feature personalizada
        system = (
            "Eres un asistente operativo de MyExcellence. Responde en español, "
            "con tono profesional. No infieras atributos discriminatorios."
        )
        user = str(masked_input.get("prompt") or masked_input)

    return system, user


# ────────────────── Validaciones de pre-call ─────────────────────────────
async def _check_ready_to_invoke(
    *, tenant_id: str, client_id: str, feature_code: str,
) -> tuple[dict | None, dict | None, dict | None, _GatewayError | None]:
    """Devuelve (feature_doc, client_config, bracket, error)."""
    feat_repo = AIFeatureRepository(tenant_id=tenant_id)
    feature = await feat_repo.by_code(feature_code)
    if not feature or not feature.get("active"):
        return None, None, None, _GatewayError(
            AI_FEATURE_NOT_FOUND, f"Feature '{feature_code}' no existe o está inactiva"
        )

    cfg_repo = AIClientConfigRepository(tenant_id=tenant_id)
    client_cfg = await cfg_repo.get(client_id)
    # R39 — opt-in explícito
    if not client_cfg or not client_cfg.get("is_active"):
        return feature, client_cfg, None, _GatewayError(
            AI_DISABLED, "Cliente no tiene IA activada (R39)."
        )
    if not client_cfg.get("opt_in_signature") or not client_cfg.get("bracket_id"):
        return feature, client_cfg, None, _GatewayError(
            AI_DISABLED, "Falta firma de opt-in o bracket asignado (R39)."
        )
    if feature_code not in (client_cfg.get("enabled_features") or []):
        return feature, client_cfg, None, _GatewayError(
            AI_DISABLED, f"Feature '{feature_code}' no habilitada para este cliente."
        )

    bracket_repo = AIBracketRepository()
    bracket = await bracket_repo.find_one({"id": client_cfg["bracket_id"]})
    if not bracket:
        return feature, client_cfg, None, _GatewayError(
            AI_DISABLED, "Bracket asignado no existe."
        )

    # R40 — tope automático
    cap_usd = client_cfg.get("monthly_cap_override_usd")
    if cap_usd is None:
        cap_usd = bracket.get("hard_cap_usd_per_month", 0)
    cons_repo = AIConsumptionRepository(tenant_id=tenant_id)
    cons = await cons_repo.get_or_init(client_id)
    if cons.get("total_cost_usd", 0) >= cap_usd:
        return feature, client_cfg, bracket, _GatewayError(
            AI_BUDGET_CAPPED, "Tope mensual alcanzado (R40)."
        )

    # Estimación previa: si la próxima invocación (avg_cost_usd) supera el cap, bloquear
    avg_next = float(feature.get("avg_cost_usd", 0))
    if cons.get("total_cost_usd", 0) + avg_next > cap_usd:
        return feature, client_cfg, bracket, _GatewayError(
            AI_BUDGET_CAPPED,
            f"La invocación excedería el tope mensual (consumido={cons['total_cost_usd']:.4f}, cap={cap_usd}).",
        )

    return feature, client_cfg, bracket, None


# ────────────────── ENTRY POINT ──────────────────────────────────────────
async def invoke(
    *,
    tenant_id: str,
    client_id: str,
    user_id: str | None,
    feature_code: str,
    raw_input: dict,
    ticket_id: str | None = None,
    request_id: str | None = None,
    usd_to_mxn: float | None = None,
) -> AIGatewayResult:
    """Invoca un feature de IA. Retorna AIGatewayResult.

    NUNCA usar otro punto del código para llamar a un proveedor de IA (R38).
    """
    log_repo = AIInvocationLogRepository(tenant_id=tenant_id)
    cons_repo = AIConsumptionRepository(tenant_id=tenant_id)
    request_id = request_id or new_id()
    fx = float(usd_to_mxn or DEFAULT_USD_TO_MXN)

    # 1) Validaciones (feature exists · opt-in · enabled_features · cap)
    feature, client_cfg, bracket, err = await _check_ready_to_invoke(
        tenant_id=tenant_id, client_id=client_id, feature_code=feature_code,
    )
    if err is not None:
        await log_repo.append({
            "client_id": client_id, "user_id": user_id,
            "feature_id": (feature or {}).get("id", "unknown"),
            "feature_code": feature_code, "ticket_id": ticket_id,
            "provider": (feature or {}).get("recommended_provider", "anthropic"),
            "model": (feature or {}).get("recommended_model", ""),
            "input_tokens": 0, "output_tokens": 0,
            "cost_usd": 0.0, "cost_mxn": 0.0, "exchange_rate": fx,
            "latency_ms": 0,
            "prompt_hash": "", "prompt_masked_preview": "",
            "response_hash": "",
            "status": "capped" if err.code == AI_BUDGET_CAPPED else "error",
            "error_code": err.code,
            "request_id": request_id,
        })
        http_status = 429 if err.code == AI_BUDGET_CAPPED else 403
        return AIGatewayResult(
            ok=False, code=err.code, message=err.message, http_status=http_status,
        )

    # 2) Enmascarar PII (R36) — antes de construir prompt
    masked_input, mapping = mask_dict(raw_input or {})

    # 3) Construir prompt con texto enmascarado
    system_msg, user_prompt = _build_prompt(feature_code, masked_input)
    prompt_hash = _hash(str(raw_input))                    # hash del original (R37 audit)
    prompt_masked_preview = (system_msg + " | " + user_prompt)[:500]

    # 4) Resolver credenciales (override por cliente o universal key)
    provider_override, api_key = _resolve_credentials(client_cfg)
    provider = client_cfg.get("custom_provider") or feature.get("recommended_provider", "anthropic")
    model = feature.get("recommended_model", "")
    if not api_key:
        await log_repo.append({
            "client_id": client_id, "user_id": user_id,
            "feature_id": feature["id"], "feature_code": feature_code,
            "ticket_id": ticket_id, "provider": provider, "model": model,
            "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "cost_mxn": 0.0,
            "exchange_rate": fx, "latency_ms": 0,
            "prompt_hash": prompt_hash, "prompt_masked_preview": prompt_masked_preview,
            "response_hash": "", "status": "provider_unavailable",
            "error_code": AI_PROVIDER_UNAVAILABLE, "request_id": request_id,
        })
        return AIGatewayResult(
            ok=False, code=AI_PROVIDER_UNAVAILABLE,
            message="No hay credencial configurada (universal key o tenant override).",
            http_status=503,
        )

    # 5) Cache lookup (P1) — sólo si la feature lo permite
    cache_enabled = bool(feature.get("cache_enabled", False))
    cached = None
    if cache_enabled:
        cached = await prompt_cache.get(tenant_id, feature_code, model, prompt_hash)

    # 6) Circuit breaker (P1) — saltar si tenemos cache hit
    if cached is None:
        allowed, reason = await breaker.allow(provider)
        if not allowed:
            await log_repo.append({
                "client_id": client_id, "user_id": user_id,
                "feature_id": feature["id"], "feature_code": feature_code,
                "ticket_id": ticket_id, "provider": provider, "model": model,
                "input_tokens": 0, "output_tokens": 0,
                "cost_usd": 0.0, "cost_mxn": 0.0, "exchange_rate": fx,
                "latency_ms": 0, "prompt_hash": prompt_hash,
                "prompt_masked_preview": prompt_masked_preview,
                "response_hash": "", "status": "provider_unavailable",
                "error_code": AI_PROVIDER_UNAVAILABLE,
                "breaker_reason": reason, "request_id": request_id,
            })
            return AIGatewayResult(
                ok=False, code=AI_PROVIDER_UNAVAILABLE,
                message=f"Proveedor en cooldown ({reason}).", http_status=503,
            )

    # 7) Llamar al proveedor (o usar cache)
    if cached is not None:
        provider_response = cached
        from_cache = True
    else:
        from_cache = False
        try:
            provider_response = await _call_provider(provider, model, system_msg, user_prompt, api_key)
            await breaker.record_success(provider)
            if cache_enabled:
                await prompt_cache.put(tenant_id, feature_code, model, prompt_hash, provider_response)
        except _GatewayError as ge:
            await breaker.record_failure(provider)
            await log_repo.append({
                "client_id": client_id, "user_id": user_id,
                "feature_id": feature["id"], "feature_code": feature_code,
                "ticket_id": ticket_id, "provider": provider, "model": model,
                "input_tokens": 0, "output_tokens": 0,
                "cost_usd": 0.0, "cost_mxn": 0.0, "exchange_rate": fx,
                "latency_ms": 0, "prompt_hash": prompt_hash,
                "prompt_masked_preview": prompt_masked_preview,
                "response_hash": "",
                "status": "provider_unavailable" if ge.code != AI_PROVIDER_TIMEOUT else "error",
                "error_code": ge.code, "request_id": request_id,
            })
            return AIGatewayResult(ok=False, code=ge.code, message=ge.message, http_status=503)

    # 6) Cálculos finales — cache hits no cuestan (input/output sí)
    in_tok = provider_response["input_tokens"]
    out_tok = provider_response["output_tokens"]
    cost_usd = 0.0 if from_cache else round(_estimate_cost_usd(model, in_tok, out_tok), 6)
    cost_mxn = round(cost_usd * fx, 4)
    response_text = provider_response["text"]
    response_hash = _hash(response_text)

    # 7) Desenmascarar SOLO si destinatario es agent_internal (R36 / R42)
    destinatario = feature.get("destinatario", "agent_internal")
    if destinatario == "agent_internal":
        unknown = detect_unknown_tokens(response_text, mapping)
        if unknown:
            log.warning("ai_unknown_tokens_in_output", extra={"context": {
                "feature_code": feature_code, "tokens": unknown[:5],
            }})
        final_text = unmask(response_text, mapping)
    else:
        final_text = response_text   # mantener tokens si va a cliente final

    # 8) Persistir log (APPEND-ONLY · R37)
    invocation_doc = await log_repo.append({
        "client_id": client_id, "user_id": user_id,
        "feature_id": feature["id"], "feature_code": feature_code,
        "ticket_id": ticket_id,
        "provider": provider, "model": model,
        "input_tokens": in_tok, "output_tokens": out_tok,
        "cost_usd": cost_usd, "cost_mxn": cost_mxn, "exchange_rate": fx,
        "latency_ms": provider_response["latency_ms"],
        "prompt_hash": prompt_hash,
        "prompt_masked_preview": prompt_masked_preview,
        "response_hash": response_hash,
        "status": "cache_hit" if from_cache else "success",
        "error_code": None,
        "request_id": request_id,
        "pii_detected": bool(mapping),
        "pii_token_count": len(mapping),
        "from_cache": from_cache,
        "destinatario": destinatario,
        "approved_at": None,
        "approved_by": None,
        "webhook_delivered": None,
    })

    # 9) Acumular consumo para topes (R40) — sólo si no es cache hit
    if not from_cache:
        cons = await cons_repo.add_consumption(
            client_id, input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost_usd,
        )

        # 10) Disparar alertas 80% / 100%
        cap_usd = client_cfg.get("monthly_cap_override_usd") or bracket["hard_cap_usd_per_month"]
        pct = (cons["total_cost_usd"] / cap_usd) * 100 if cap_usd else 0
        threshold_pct = bracket.get("alert_threshold_pct", 80)
        if pct >= threshold_pct and not cons.get("alert_80_sent_at"):
            await cons_repo.mark_alert_sent(client_id, threshold=80)
        if cons["total_cost_usd"] >= cap_usd and not cons.get("alert_100_sent_at"):
            await cons_repo.mark_alert_sent(client_id, threshold=100)

    # 11) R42 — destinatario client_final ⇒ draft=true
    is_draft = destinatario in ("client_final", "both")

    return AIGatewayResult(ok=True, http_status=200, data={
        "feature_code": feature_code,
        "output": {
            "text": final_text,
            "tokens_used": in_tok + out_tok,
        },
        "draft": is_draft,
        "invocation_id": invocation_doc["id"],
        "cost_estimate_mxn": cost_mxn,
        "cost_estimate_usd": cost_usd,
        "model": model,
        "provider": provider,
        "from_cache": from_cache,
        "pii_tokens_in_output": detect_unknown_tokens(response_text, mapping)
            if destinatario != "agent_internal" else [],
    })


# Encrypt helper para `custom_api_key` cuando el admin lo guarda
def encrypt_custom_key(api_key: str) -> str:
    return encrypt_str(api_key)
