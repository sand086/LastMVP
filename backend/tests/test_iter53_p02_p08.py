"""Tests for iteration 53 — P02 (health), P03 (global rate limit), P04 (circuit breaker)."""
import os
import time
import requests
import concurrent.futures

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://lastmile-mvp.preview.emergentagent.com").rstrip("/")


# P02 — Health endpoint
class TestHealthEndpoint:
    def test_health_no_auth_required(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=5)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"

    def test_health_response_under_500ms(self):
        start = time.time()
        r = requests.get(f"{BASE_URL}/api/health", timeout=5)
        elapsed = (time.time() - start) * 1000
        assert r.status_code == 200
        assert elapsed < 1500, f"Response took {elapsed}ms (expected <1500ms server-side has elapsed_ms)"
        body = r.json()
        assert body.get("elapsed_ms", 9999) < 500, f"Server elapsed_ms={body.get('elapsed_ms')}"

    def test_health_payload_structure(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=5)
        body = r.json()
        assert body["status"] in ("healthy", "degraded", "unhealthy")
        assert "version" in body
        assert "elapsed_ms" in body
        assert "checks" in body
        for key in ("database", "ai_eval_worker", "kosmo_sync", "storage", "circuit_breakers"):
            assert key in body["checks"], f"missing check: {key}"

    def test_health_database_collections_accessible(self):
        body = requests.get(f"{BASE_URL}/api/health", timeout=5).json()
        assert body["checks"]["database"]["collections_accessible"] > 0

    def test_health_storage_warning_persistence(self):
        body = requests.get(f"{BASE_URL}/api/health", timeout=5).json()
        warning = body["checks"]["storage"].get("warning", "")
        assert "do not persist" in warning.lower(), f"warning was: {warning}"

    # P04 — Circuit breaker structure
    def test_health_circuit_breakers_is_dict(self):
        body = requests.get(f"{BASE_URL}/api/health", timeout=5).json()
        cb = body["checks"]["circuit_breakers"]
        assert isinstance(cb, dict), f"circuit_breakers should be dict, got {type(cb)}"


# P03 — Global rate limit middleware
class TestGlobalRateLimit:
    def test_health_excluded_from_rate_limit(self):
        """50 quick GETs to /api/health should never 429 (excluded). Uses reused session."""
        sess = requests.Session()
        ok = 0
        too_many = 0
        for _ in range(50):
            try:
                r = sess.get(f"{BASE_URL}/api/health", timeout=10)
            except Exception:
                continue
            if r.status_code == 200:
                ok += 1
            elif r.status_code == 429:
                too_many += 1
        assert too_many == 0, f"/api/health was rate-limited {too_many} times (should be excluded)"
        assert ok >= 45, f"Only {ok}/50 succeeded"

    def test_global_rate_limit_returns_429(self):
        """Anon rate limit is 300/min per IP. Ingress balances 2 IPs, so fire 700 sequentially."""
        results = {"200": 0, "401": 0, "403": 0, "429": 0, "other": 0}
        retry_after_present = False
        body_ok = False
        sess = requests.Session()
        for i in range(700):
            try:
                r = sess.get(f"{BASE_URL}/api/dashboard/stats", timeout=8)
            except Exception:
                results["other"] += 1
                continue
            code = r.status_code
            if code == 429:
                results["429"] += 1
                if r.headers.get("Retry-After") == "60":
                    retry_after_present = True
                try:
                    if r.json().get("error") == "rate_limit_exceeded":
                        body_ok = True
                except Exception:
                    pass
            elif code in (200, 401, 403):
                results[str(code)] += 1
            else:
                results["other"] += 1
            # Early-exit once we've confirmed
            if results["429"] >= 5 and retry_after_present and body_ok:
                break
        print(f"Rate limit results: {results}")
        assert results["429"] > 0, f"Expected 429 responses, got {results}"
        assert retry_after_present, "Retry-After: 60 header missing on 429"
        assert body_ok, "Body should contain {error: 'rate_limit_exceeded'}"
