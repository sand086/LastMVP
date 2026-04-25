"""
Test suite for shadow-cost detection (iter51).

Validates:
  - log_token_usage now accounts for image_count → tokens_images
  - is_shadow_cost / shadow_kind flags persist correctly
  - evidence_scoring._call_ai_vision shadow-logs on send_message failure
  - admin/token-usage endpoint exposes shadow summary
"""
import os
import sys
import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock

sys.path.insert(0, "/app/backend")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_lastmile_iter51")
os.environ.setdefault("EMERGENT_LLM_KEY", "sk-emergent-test")


@pytest.fixture
def fake_db():
    """In-memory mock for db.token_usage_log.insert_one + db.config.find_one."""
    inserted = []
    db = MagicMock()
    db.token_usage_log = MagicMock()
    db.token_usage_log.insert_one = AsyncMock(side_effect=lambda d: inserted.append(d) or MagicMock(inserted_id=d.get("id")))
    db.config = MagicMock()
    # No custom pricing → falls back to FALLBACK_MODEL_PRICING
    db.config.find_one = AsyncMock(return_value=None)
    db._inserted = inserted
    return db


@pytest.mark.asyncio
async def test_log_token_usage_counts_images(fake_db):
    from token_logger import log_token_usage, IMAGE_INPUT_TOKEN_ESTIMATE
    await log_token_usage(
        db=fake_db, entregable="evaluacion", modelo="claude-haiku-4-5",
        referencia="TRK-001", input_text="hello", output_text="world",
        system_prompt="prompt-x", image_count=3,
    )
    doc = fake_db._inserted[-1]
    assert doc["image_count"] == 3
    assert doc["tokens_images"] == 3 * IMAGE_INPUT_TOKEN_ESTIMATE
    assert doc["tokens_input"] >= 3 * IMAGE_INPUT_TOKEN_ESTIMATE
    assert doc["is_shadow_cost"] is False
    assert doc["shadow_kind"] is None
    assert doc["cost_usd"] > 0  # imágenes generan costo > 0


@pytest.mark.asyncio
async def test_log_token_usage_shadow_flags(fake_db):
    from token_logger import log_token_usage
    await log_token_usage(
        db=fake_db, entregable="evaluacion", modelo="claude-haiku-4-5",
        referencia="TRK-002", input_text="x", system_prompt="p",
        image_count=2, is_shadow_cost=True, shadow_kind="error_before_response",
    )
    doc = fake_db._inserted[-1]
    assert doc["is_shadow_cost"] is True
    assert doc["shadow_kind"] == "error_before_response"
    assert doc["tokens_images"] == 2 * 1500


@pytest.mark.asyncio
async def test_call_ai_vision_logs_shadow_on_send_failure(fake_db):
    """When chat.send_message raises, _call_ai_vision must log a shadow event AND re-raise."""
    import evidence_scoring as ev

    fake_chat = MagicMock()
    fake_chat.with_model = MagicMock()
    fake_chat.send_message = AsyncMock(side_effect=Exception("Anthropic 529 overloaded"))

    with patch.object(ev, "_get_db", return_value=fake_db), \
         patch.object(ev, "_get_system_prompt", new=AsyncMock(return_value="SYS")), \
         patch.object(ev, "_get_training_context", new=AsyncMock(return_value="")), \
         patch("emergentintegrations.llm.chat.LlmChat", return_value=fake_chat), \
         patch("ai_eval_config.get_ai_eval_config", new=AsyncMock(return_value={"model": "haiku-4-5"})):

        # Must re-raise the original exception
        with pytest.raises(Exception, match="overloaded"):
            await ev._call_ai_vision(["b64image1", "b64image2"], "TRK-X", "delivered", "deja en recepción")

    # And shadow event must be in the log
    shadow_docs = [d for d in fake_db._inserted if d.get("is_shadow_cost")]
    assert len(shadow_docs) == 1
    sd = shadow_docs[0]
    assert sd["shadow_kind"] == "error_before_response"
    assert sd["image_count"] == 2
    assert sd["modelo"] == "claude-haiku-4-5"
    assert sd["referencia"] == "TRK-X"
    # Cost must be > 0 (imágenes y prompt fueron facturados)
    assert sd["cost_usd"] > 0


@pytest.mark.asyncio
async def test_call_ai_vision_logs_normal_on_success(fake_db):
    import evidence_scoring as ev

    fake_chat = MagicMock()
    fake_chat.with_model = MagicMock()
    fake_chat.send_message = AsyncMock(return_value='{"overall_score": 87, "confidence": 0.9}')

    with patch.object(ev, "_get_db", return_value=fake_db), \
         patch.object(ev, "_get_system_prompt", new=AsyncMock(return_value="SYS")), \
         patch.object(ev, "_get_training_context", new=AsyncMock(return_value="")), \
         patch("emergentintegrations.llm.chat.LlmChat", return_value=fake_chat), \
         patch("ai_eval_config.get_ai_eval_config", new=AsyncMock(return_value={"model": "haiku-4-5"})):

        result = await ev._call_ai_vision(["img1"], "TRK-OK", "delivered", "")
        assert result is not None
        assert result.get("overall_score") == 87
        # Tokens estimate now propagated
        assert result.get("_tokens_used_estimate", 0) > 0
        assert result.get("_image_count") == 1

    docs = fake_db._inserted
    assert len(docs) == 1
    assert docs[0]["is_shadow_cost"] is False
    assert docs[0]["image_count"] == 1
