"""
Iteration 49 backend tests:
- GET /api/ai-evaluation/health (P0 fix — ImportError resolved)
- GET /api/ai-evaluation/config (dynamic config)
- GET /api/reports/kpis (day/week/month group_by for TrendsTab)
- Regression: /api/admin/summary still returns 200 (Motor IA tab)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://lastmile-mvp.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def dev_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "dev@me.mx", "password": "LastMile2026"}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("access_token") or data.get("token")
    assert tok, f"no token in response: {data}"
    return tok


@pytest.fixture(scope="module")
def h(dev_token):
    return {"Authorization": f"Bearer {dev_token}"}


# ---------- /api/ai-evaluation/health ----------

class TestAiEvaluationHealth:
    def test_health_returns_200(self, h):
        r = requests.get(f"{BASE_URL}/api/ai-evaluation/health", headers=h, timeout=30)
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"

    def test_health_payload_shape(self, h):
        r = requests.get(f"{BASE_URL}/api/ai-evaluation/health", headers=h, timeout=30)
        data = r.json()
        # Required top-level keys
        assert "status" in data
        assert "worker" in data
        assert "queue" in data
        assert "last_terminal_job" in data
        # Worker nested fields
        w = data["worker"]
        for key in ["max_concurrent", "slots_in_use", "slots_free", "cron_interval_minutes"]:
            assert key in w, f"missing worker.{key}: {w}"
        # max_concurrent should be a positive int (from dynamic config)
        assert isinstance(w["max_concurrent"], int) and w["max_concurrent"] > 0
        assert isinstance(w["slots_in_use"], int)
        assert isinstance(w["slots_free"], int)


# ---------- /api/ai-evaluation/config ----------

class TestAiEvaluationConfig:
    def test_config_returns_200(self, h):
        r = requests.get(f"{BASE_URL}/api/ai-evaluation/config", headers=h, timeout=30)
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"

    def test_config_payload_shape(self, h):
        r = requests.get(f"{BASE_URL}/api/ai-evaluation/config", headers=h, timeout=30)
        data = r.json()
        # Response envelope: {config, defaults, bounds, model_map, pause_state}
        assert "config" in data, f"missing envelope.config: keys={list(data.keys())}"
        cfg = data["config"]
        required = [
            "model", "timeout_per_guia", "max_routes_concurrent",
            "batch_size_per_route", "max_retries", "paused_until",
            "schedule_enabled", "schedule_windows",
        ]
        for key in required:
            assert key in cfg, f"missing config.{key}: keys={list(cfg.keys())}"
        assert isinstance(cfg["max_routes_concurrent"], int) and cfg["max_routes_concurrent"] > 0
        assert isinstance(cfg["schedule_enabled"], bool)
        assert isinstance(cfg["schedule_windows"], list)


# ---------- /api/reports/kpis ----------

class TestReportsKpis:
    def _fetch(self, h, group_by):
        url = f"{BASE_URL}/api/reports/kpis"
        params = {"date_from": "2026-04-01", "date_to": "2026-04-24", "group_by": group_by}
        return requests.get(url, headers=h, params=params, timeout=60)

    def test_kpis_day(self, h):
        r = self._fetch(h, "day")
        assert r.status_code == 200, f"day: {r.status_code} {r.text}"
        data = r.json()
        assert "data" in data and isinstance(data["data"], list)
        assert "summary" in data
        assert "has_data" in data
        assert isinstance(data["has_data"], bool)

    def test_kpis_week(self, h):
        r = self._fetch(h, "week")
        assert r.status_code == 200, f"week: {r.status_code} {r.text}"
        data = r.json()
        assert "data" in data and isinstance(data["data"], list)
        assert "summary" in data
        assert "has_data" in data

    def test_kpis_month(self, h):
        r = self._fetch(h, "month")
        assert r.status_code == 200, f"month: {r.status_code} {r.text}"
        data = r.json()
        assert "data" in data and isinstance(data["data"], list)
        assert "summary" in data
        assert "has_data" in data

    def test_kpis_data_row_shape(self, h):
        """If has_data, every row should have a time-bucket key (date/week/month)."""
        r = self._fetch(h, "day")
        data = r.json()
        if data["has_data"] and data["data"]:
            row = data["data"][0]
            # Must have some form of period/date identifier
            assert any(k in row for k in ["group", "date", "period", "bucket", "day", "week", "month"]), (
                f"row missing time key: {row}"
            )


# ---------- Regression: admin summary (Motor IA tab still works) ----------

class TestAdminSummaryRegression:
    def test_admin_summary_200(self, h):
        r = requests.get(f"{BASE_URL}/api/admin/summary?period=current_month", headers=h, timeout=30)
        assert r.status_code == 200, f"got {r.status_code}: {r.text}"
