"""
Token usage logging helper for AI calls.
Estimates token counts from text length since emergentintegrations doesn't expose usage data.
"""
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Fallback pricing (USD per million tokens) used when `ia_cost_config` doesn't list the model.
# Kept in sync with Anthropic / OpenAI public pricing so new models cost > 0 from day 1.
FALLBACK_MODEL_PRICING = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-opus-4-5": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-6": (15.0, 75.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
    "gpt-5.2": (5.0, 20.0),
    "gpt-5.1": (5.0, 20.0),
}


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English/Spanish."""
    if not text:
        return 0
    return max(1, len(text) // 4)


async def log_token_usage(
    db,
    entregable: str,
    modelo: str,
    referencia: str,
    input_text: str = "",
    output_text: str = "",
    system_prompt: str = "",
    journey_id: str = None,
    guide: str = None,
    client_id: str = None,
    user_id: str = None,
):
    """
    Log AI token usage to token_usage_log collection.
    Non-blocking: errors are caught and logged, never bubbled up.
    """
    try:
        tokens_input = _estimate_tokens(input_text)
        tokens_output = _estimate_tokens(output_text)
        tokens_prompt = _estimate_tokens(system_prompt)
        tokens_total = tokens_input + tokens_output + tokens_prompt

        # Get cost config
        cost_doc = await db.config.find_one({"key": "ia_cost_config"}, {"_id": 0})
        tc_doc = await db.config.find_one({"key": "exchange_rate"}, {"_id": 0})

        cost_usd = 0.0
        cost_mxn = 0.0
        tc = 19.0

        if tc_doc and tc_doc.get("value"):
            tc = tc_doc["value"].get("rate", 19.0)

        input_per_m = None
        output_per_m = None
        if cost_doc and cost_doc.get("value", {}).get("models"):
            models = cost_doc["value"]["models"]
            model_cfg = next((m for m in models if m["name"] == modelo), None)
            if model_cfg:
                input_per_m = model_cfg.get("input_per_million", 0)
                output_per_m = model_cfg.get("output_per_million", 0)

        # Fallback to hard-coded pricing if the model isn't in config
        if input_per_m is None and modelo in FALLBACK_MODEL_PRICING:
            input_per_m, output_per_m = FALLBACK_MODEL_PRICING[modelo]
            logger.info(f"Using fallback pricing for {modelo}: ${input_per_m}/${output_per_m} per M")

        if input_per_m is not None:
            input_cost = (tokens_input / 1_000_000) * input_per_m
            output_cost = (tokens_output / 1_000_000) * output_per_m
            cost_usd = round(input_cost + output_cost, 6)
            cost_mxn = round(cost_usd * tc, 4)

        now = datetime.now(timezone.utc).isoformat()

        doc = {
            "id": str(uuid.uuid4()),
            "timestamp": now,
            "entregable": entregable,
            "modelo": modelo,
            "referencia": referencia[:120] if referencia else "",
            "journey_id": journey_id,
            "guide": guide,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "tokens_prompt": tokens_prompt,
            "tokens_total": tokens_total,
            "cost_usd": cost_usd,
            "cost_mxn": cost_mxn,
            "client_id": client_id,
            "user_id": user_id,
        }

        await db.token_usage_log.insert_one(doc)
        logger.debug(f"Token usage logged: {entregable} / {modelo} / {tokens_total} tokens / ${cost_usd}")

    except Exception as e:
        logger.warning(f"Failed to log token usage (non-blocking): {e}")
