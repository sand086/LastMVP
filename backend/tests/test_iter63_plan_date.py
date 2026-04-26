"""Unit tests for _extract_plan_date — fix for journey.date discrepancy vs Routal."""
from datetime import datetime, timezone
from workers.routal_event_processor import _extract_plan_date


class TestExtractPlanDate:
    def test_execution_date_iso_z(self):
        # Real Routal payload format (from API)
        payload = {"execution_date": "2026-04-26T18:00:00.000Z"}
        assert _extract_plan_date(payload) == "2026-04-26"

    def test_execution_date_with_offset(self):
        payload = {"execution_date": "2026-04-26T18:00:00+00:00"}
        assert _extract_plan_date(payload) == "2026-04-26"

    def test_execution_date_overrides_date_field(self):
        # If both are present, execution_date wins (authoritative)
        payload = {
            "execution_date": "2026-04-26T18:00:00.000Z",
            "date": "2026-04-25",  # buggy field
        }
        assert _extract_plan_date(payload) == "2026-04-26"

    def test_date_field_plain_string(self):
        payload = {"date": "2026-04-26"}
        assert _extract_plan_date(payload) == "2026-04-26"

    def test_date_field_iso(self):
        payload = {"date": "2026-04-26T00:00:00Z"}
        assert _extract_plan_date(payload) == "2026-04-26"

    def test_no_date_falls_back_to_today_utc(self):
        payload = {}
        result = _extract_plan_date(payload)
        expected = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert result == expected

    def test_invalid_execution_date_falls_back_to_date(self):
        payload = {"execution_date": "not-a-date", "date": "2026-04-26"}
        assert _extract_plan_date(payload) == "2026-04-26"

    def test_invalid_both_falls_back_to_today(self):
        payload = {"execution_date": "garbage", "date": "also-garbage"}
        result = _extract_plan_date(payload)
        expected = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert result == expected

    def test_real_world_april_26_plan(self):
        """Reproduces user-reported discrepancy: Routal plan 69ee28ea0b5c1d1cc8ba6704
        execution_date=2026-04-26T18:00:00.000Z (label "2026/04/26 - Plan").
        Old code with payload.date='2026-04-25' produced 25; new code returns 26.
        """
        payload = {
            "id": "69ee28ea0b5c1d1cc8ba6704",
            "execution_date": "2026-04-26T18:00:00.000Z",
            "date": "2026-04-25",  # hypothetical buggy webhook field
            "driver": {"id": "driver_0Ojnl5hju5X1HN", "name": "Ildefonso Ignacio Piedra Buena Salgado"},
        }
        assert _extract_plan_date(payload) == "2026-04-26"
