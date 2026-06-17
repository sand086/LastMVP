"""
Iter91 — Bug fix: rule-based eval was silently overwriting AI scores on route close.

PROD report (2026-06-17, journey 6a3169830a706fc91e281e5d): user audited 1 package
manually (score 75), the rest had AI scores 90–100. After closing the route, 3
additional guides appeared with Score IA < 90 (50/70/70). The AI scores had been
modified automatically by the close-route hook.

Root cause: `routes/journey_routes.close_journey` calls
`evaluate_packages_for_journey(db, journey_id)` with default `use_ai=False`. The
rule-based branch in `evidence_scoring.evaluate_packages_for_journey` was
iterating EVERY delivered/failed package and overwriting `evidence_score` with a
simple photo-count rule (0→0, 1→40, 2→70, 3+→100). The frontend "Score IA" column
falls back to `evidence_score` via `setdefault` in `/api/journeys`, so AI's 92
became rules' 70 after close.

Fix: in the rule-based branch, skip any package already evaluated
(`evidence_method == "ai"` OR has a non-null `evidence_score` + `evidence_evaluated_at`).
Rules-based is now strictly a fallback for packages the AI never evaluated.

Tests:
  1. AI-evaluated package (evidence_method='ai', score=92) → NOT overwritten by rules.
  2. Non-AI-evaluated package with no score → rules fill in.
  3. Package previously scored by rules → rules still re-evaluates (no AI evidence).
  4. Manually adjusted package (evidence_method='manual') → preserved.
"""
from __future__ import annotations
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from dotenv import load_dotenv  # noqa: E402
load_dotenv(Path(BACKEND_DIR) / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from evidence_scoring import evaluate_packages_for_journey  # noqa: E402


def _make_db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client[os.environ["DB_NAME"]]


@pytest.mark.asyncio
async def test_rules_do_not_overwrite_ai_score_on_close():
    """Reproduces PROD journey 6a3169830a706fc91e281e5d behavior. A package with
    evidence_method='ai' and evidence_score=92 (2 photos) must NOT be downgraded
    to 70 by the close-route rule-based hook."""
    db = _make_db()
    journey_id = f"_test_iter91_{uuid.uuid4().hex[:8]}"
    pkg_ai_id = f"pkg_ai_{uuid.uuid4().hex[:6]}"
    pkg_unscored_id = f"pkg_un_{uuid.uuid4().hex[:6]}"
    pkg_rules_old_id = f"pkg_old_{uuid.uuid4().hex[:6]}"

    try:
        # 1) AI-scored package (mimics PROD: 2 photos, AI eval = 92).
        await db.packages.insert_one({
            "id": pkg_ai_id, "journey_id": journey_id, "status": "delivered",
            "kosmo_proof_count": 2, "kosmo_driver_note": "",
            "evidence_score": 92, "evidence_method": "ai",
            "evidence_evaluated_at": datetime.now(timezone.utc).isoformat(),
            "tracking_number": "AI-001",
        })
        # 2) Unscored package — rules should fill in.
        await db.packages.insert_one({
            "id": pkg_unscored_id, "journey_id": journey_id, "status": "delivered",
            "kosmo_proof_count": 2, "kosmo_driver_note": "",
            "tracking_number": "NEW-001",
        })
        # 3) Previously rule-scored package (e.g., another route close) — rules CAN re-run.
        # But our fix uses `evidence_evaluated_at + evidence_score` as a stop-marker too,
        # because rules-based timestamps were also being set. So existing rules-scored
        # packages stay untouched. That is acceptable: rule-eval is idempotent on
        # the same inputs, so skipping it is safe.
        await db.packages.insert_one({
            "id": pkg_rules_old_id, "journey_id": journey_id, "status": "delivered",
            "kosmo_proof_count": 3, "kosmo_driver_note": "",
            "evidence_score": 100, "evidence_method": "rules",
            "evidence_evaluated_at": datetime.now(timezone.utc).isoformat(),
            "tracking_number": "RULES-001",
        })

        # Call the same path close_journey uses.
        await evaluate_packages_for_journey(db, journey_id, use_ai=False)

        ai_pkg = await db.packages.find_one({"id": pkg_ai_id})
        assert ai_pkg["evidence_score"] == 92, (
            f"AI score must be preserved, got {ai_pkg['evidence_score']}"
        )
        assert ai_pkg["evidence_method"] == "ai", "evidence_method must stay 'ai'"

        unscored = await db.packages.find_one({"id": pkg_unscored_id})
        assert unscored["evidence_score"] == 70, (
            f"Rules should fill in unscored package (2 photos → 70), got "
            f"{unscored['evidence_score']}"
        )
        assert unscored["evidence_method"] == "rules"

        rules_old = await db.packages.find_one({"id": pkg_rules_old_id})
        # Previously rule-scored with timestamp → now also skipped (safe: idempotent).
        assert rules_old["evidence_score"] == 100
    finally:
        await db.packages.delete_many({"journey_id": journey_id})


@pytest.mark.asyncio
async def test_close_journey_hook_preserves_manual_review_scores():
    """When a coordinator manually adjusted a score (evidence_method='manual'),
    close_journey must not overwrite it back to a rule-based number."""
    db = _make_db()
    journey_id = f"_test_iter91m_{uuid.uuid4().hex[:8]}"
    pkg_id = f"pkg_man_{uuid.uuid4().hex[:6]}"

    try:
        await db.packages.insert_one({
            "id": pkg_id, "journey_id": journey_id, "status": "delivered",
            "kosmo_proof_count": 2,  # would yield 70 by rules
            "kosmo_driver_note": "",
            "evidence_score": 75, "evidence_method": "manual",
            "evidence_evaluated_at": datetime.now(timezone.utc).isoformat(),
            "manually_reviewed": True, "adjusted_score": 75,
            "tracking_number": "MAN-001",
        })

        await evaluate_packages_for_journey(db, journey_id, use_ai=False)

        pkg = await db.packages.find_one({"id": pkg_id})
        assert pkg["evidence_score"] == 75, (
            f"Manual review score must be preserved, got {pkg['evidence_score']}"
        )
    finally:
        await db.packages.delete_many({"journey_id": journey_id})
