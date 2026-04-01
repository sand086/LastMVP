"""
Iteration 25 - Code Quality Improvements Regression Tests

Tests for:
1. Backend regression: POST /api/auth/login returns access_token
2. Backend regression: GET /api/system/health returns api_status ok
3. Backend regression: GET /api/system/config returns backend_version
4. Backend regression: GET /api/admin/summary returns data with by_entregable key
5. Backend regression: GET /api/admin/routes-report returns routes
6. Backend regression: POST /api/system/integrity/run executes checks
7. Backend regression: GET /api/dashboard/stats returns data
8. Backend regression: POST /api/upload/history-orders accepts developer role (was 403 before)
9. Backend regression: POST /api/journeys/from-cosmo accepts developer role (was 403 before)
"""
import os
import pytest
import requests

# Load from conftest
from conftest import (
    TEST_API_URL, TEST_DEV_EMAIL, TEST_DEV_PASSWORD,
    TEST_COORD_EMAIL, TEST_COORD_PASSWORD
)

BASE_URL = TEST_API_URL


class TestAuthRegression:
    """Test authentication endpoints still work after refactoring"""
    
    def test_login_returns_access_token(self):
        """POST /api/auth/login returns access_token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_DEV_EMAIL,
            "password": TEST_DEV_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, f"Missing access_token in response: {data}"
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0
        assert "user" in data
        print(f"✓ Login returns access_token (length: {len(data['access_token'])})")


class TestSystemHealthRegression:
    """Test system health endpoints after system_routes.py refactoring"""
    
    @pytest.fixture
    def dev_token(self):
        """Get developer token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_DEV_EMAIL,
            "password": TEST_DEV_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Could not get dev token")
    
    @pytest.fixture
    def coord_token(self):
        """Get coordinator token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_COORD_EMAIL,
            "password": TEST_COORD_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Could not get coordinator token")
    
    def test_system_health_returns_api_status_ok(self, dev_token):
        """GET /api/system/health returns api_status ok"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/system/health", headers=headers)
        assert response.status_code == 200, f"Health check failed: {response.text}"
        data = response.json()
        assert "api_status" in data, f"Missing api_status: {data}"
        assert data["api_status"] == "ok", f"API status not ok: {data['api_status']}"
        assert "mongo_status" in data
        assert "uptime" in data
        print(f"✓ System health: api_status={data['api_status']}, mongo={data['mongo_status']}")
    
    def test_system_config_returns_backend_version(self, dev_token):
        """GET /api/system/config returns backend_version"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/system/config", headers=headers)
        assert response.status_code == 200, f"Config failed: {response.text}"
        data = response.json()
        assert "backend_version" in data, f"Missing backend_version: {data}"
        assert "FastAPI" in data["backend_version"], f"Unexpected version: {data['backend_version']}"
        assert "python_version" in data
        assert "db_name" in data
        print(f"✓ System config: backend_version={data['backend_version']}")
    
    def test_system_performance_endpoint(self, dev_token):
        """GET /api/system/performance returns metrics"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/system/performance", headers=headers)
        assert response.status_code == 200, f"Performance failed: {response.text}"
        data = response.json()
        assert "requests_per_hour" in data or "slowest_endpoints" in data
        print(f"✓ System performance endpoint working")
    
    def test_integrity_run_executes_checks(self, dev_token):
        """POST /api/system/integrity/run executes checks"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.post(f"{BASE_URL}/api/system/integrity/run", headers=headers)
        assert response.status_code == 200, f"Integrity run failed: {response.text}"
        data = response.json()
        assert "total_issues" in data or "issues" in data, f"Missing issues data: {data}"
        print(f"✓ Integrity check executed: {data.get('total_issues', 0)} issues found")


class TestAdminModuleRegression:
    """Test admin module after admin_module_routes.py refactoring"""
    
    @pytest.fixture
    def dev_token(self):
        """Get developer token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_DEV_EMAIL,
            "password": TEST_DEV_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Could not get dev token")
    
    def test_admin_summary_returns_by_entregable(self, dev_token):
        """GET /api/admin/summary returns data with by_entregable key"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/summary", headers=headers)
        assert response.status_code == 200, f"Admin summary failed: {response.text}"
        data = response.json()
        assert "by_entregable" in data, f"Missing by_entregable key: {data.keys()}"
        assert "totals" in data, f"Missing totals key: {data.keys()}"
        print(f"✓ Admin summary: by_entregable keys={list(data['by_entregable'].keys())}")
    
    def test_admin_routes_report_returns_routes(self, dev_token):
        """GET /api/admin/routes-report returns routes"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {"date_from": "2026-01-01", "date_to": "2026-12-31"}
        response = requests.get(f"{BASE_URL}/api/admin/routes-report", headers=headers, params=params)
        assert response.status_code == 200, f"Routes report failed: {response.text}"
        data = response.json()
        assert "rows" in data, f"Missing rows key: {data.keys()}"
        assert "totals" in data, f"Missing totals key: {data.keys()}"
        assert "pagination" in data, f"Missing pagination key: {data.keys()}"
        print(f"✓ Routes report: {len(data['rows'])} rows, totals={data['totals']}")
    
    def test_admin_config_endpoint(self, dev_token):
        """GET /api/admin/config returns configuration"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/admin/config", headers=headers)
        assert response.status_code == 200, f"Admin config failed: {response.text}"
        data = response.json()
        assert "ia_cost_config" in data or "exchange_rate" in data or "budget_alerts" in data
        print(f"✓ Admin config endpoint working")


class TestDashboardRegression:
    """Test dashboard stats endpoint"""
    
    @pytest.fixture
    def dev_token(self):
        """Get developer token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_DEV_EMAIL,
            "password": TEST_DEV_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Could not get dev token")
    
    def test_dashboard_stats_returns_data(self, dev_token):
        """GET /api/dashboard/stats returns data"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=headers)
        assert response.status_code == 200, f"Dashboard stats failed: {response.text}"
        data = response.json()
        # Check for expected keys
        expected_keys = ["active_journeys", "total_packages", "delivered_packages", "open_incidents"]
        for key in expected_keys:
            assert key in data, f"Missing key {key} in dashboard stats: {data.keys()}"
        print(f"✓ Dashboard stats: active={data.get('active_journeys')}, delivered={data.get('delivered_packages')}")


class TestDeveloperRoleAccess:
    """Test that developer role now has access to upload and from-cosmo endpoints"""
    
    @pytest.fixture
    def dev_token(self):
        """Get developer token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_DEV_EMAIL,
            "password": TEST_DEV_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Could not get dev token")
    
    def test_developer_can_access_upload_history_orders(self, dev_token):
        """POST /api/upload/history-orders accepts developer role (was 403 before)"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        # Create a minimal CSV file for testing
        import io
        csv_content = "order_id,order_reference_id,tracking_url\nROUTE001,REF001,https://example.com/track/1"
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        
        response = requests.post(f"{BASE_URL}/api/upload/history-orders", headers=headers, files=files)
        # Should NOT be 403 anymore - developer role should be allowed
        assert response.status_code != 403, f"Developer still getting 403 on upload/history-orders: {response.text}"
        # Should be 200 (success) or 400 (validation error) but not 403
        assert response.status_code in [200, 400, 422], f"Unexpected status: {response.status_code} - {response.text}"
        print(f"✓ Developer can access upload/history-orders (status: {response.status_code})")
    
    def test_developer_can_access_journeys_from_cosmo(self, dev_token):
        """POST /api/journeys/from-cosmo accepts developer role (was 403 before)"""
        headers = {"Authorization": f"Bearer {dev_token}", "Content-Type": "application/json"}
        # Minimal payload for testing access
        payload = {
            "date": "2026-01-15",
            "client_id": "test-client-id",
            "history_orders": [],
            "route_summary": [],
            "messenger_provider_mappings": []
        }
        
        response = requests.post(f"{BASE_URL}/api/journeys/from-cosmo", headers=headers, json=payload)
        # Should NOT be 403 anymore - developer role should be allowed
        assert response.status_code != 403, f"Developer still getting 403 on journeys/from-cosmo: {response.text}"
        # Should be 200 (success) or 400/422 (validation error) but not 403
        assert response.status_code in [200, 400, 422], f"Unexpected status: {response.status_code} - {response.text}"
        print(f"✓ Developer can access journeys/from-cosmo (status: {response.status_code})")


class TestDependenciesRefactoring:
    """Test that dependencies.py refactoring didn't break address normalization"""
    
    @pytest.fixture
    def dev_token(self):
        """Get developer token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_DEV_EMAIL,
            "password": TEST_DEV_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Could not get dev token")
    
    def test_journeys_endpoint_works(self, dev_token):
        """GET /api/journeys works after dependencies refactoring"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/journeys", headers=headers)
        assert response.status_code == 200, f"Journeys failed: {response.text}"
        data = response.json()
        assert "data" in data or isinstance(data, list), f"Unexpected response format: {type(data)}"
        print(f"✓ Journeys endpoint working after dependencies refactoring")
    
    def test_packages_search_works(self, dev_token):
        """GET /api/packages/search works after dependencies refactoring"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        response = requests.get(f"{BASE_URL}/api/packages/search?q=test", headers=headers)
        # Should work or return empty results
        assert response.status_code in [200, 404], f"Package search failed: {response.text}"
        print(f"✓ Package search endpoint working (status: {response.status_code})")


class TestConfTestEnvVars:
    """Test that conftest.py properly loads credentials from env vars"""
    
    def test_conftest_credentials_loaded(self):
        """Verify conftest credentials are loaded"""
        assert TEST_API_URL is not None
        assert TEST_DEV_EMAIL is not None
        assert TEST_DEV_PASSWORD is not None
        assert "lastmile" in TEST_API_URL.lower() or "localhost" in TEST_API_URL.lower()
        print(f"✓ Conftest credentials loaded: API_URL={TEST_API_URL}, DEV_EMAIL={TEST_DEV_EMAIL}")
    
    def test_login_with_conftest_credentials(self):
        """Login works with conftest credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_DEV_EMAIL,
            "password": TEST_DEV_PASSWORD
        })
        assert response.status_code == 200, f"Login with conftest creds failed: {response.text}"
        print(f"✓ Login successful with conftest credentials")


class TestHelperFunctionsRefactoring:
    """Test that helper function extraction in admin_module_routes.py works correctly"""
    
    @pytest.fixture
    def dev_token(self):
        """Get developer token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_DEV_EMAIL,
            "password": TEST_DEV_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Could not get dev token")
    
    def test_routes_report_row_structure(self, dev_token):
        """Routes report rows have correct structure after _build_report_row extraction"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {"date_from": "2026-01-01", "date_to": "2026-12-31"}
        response = requests.get(f"{BASE_URL}/api/admin/routes-report", headers=headers, params=params)
        assert response.status_code == 200
        data = response.json()
        
        if data.get("rows") and len(data["rows"]) > 0:
            row = data["rows"][0]
            # Check expected fields from _build_report_row
            expected_fields = ["order_id", "fecha", "driver", "proveedor", "total_paquetes", "completados"]
            for field in expected_fields:
                assert field in row, f"Missing field {field} in report row: {row.keys()}"
            print(f"✓ Routes report row structure correct: {list(row.keys())[:6]}...")
        else:
            print(f"✓ Routes report working (no rows in date range)")
    
    def test_routes_report_totals_structure(self, dev_token):
        """Routes report totals have correct structure"""
        headers = {"Authorization": f"Bearer {dev_token}"}
        params = {"date_from": "2026-01-01", "date_to": "2026-12-31"}
        response = requests.get(f"{BASE_URL}/api/admin/routes-report", headers=headers, params=params)
        assert response.status_code == 200
        data = response.json()
        
        totals = data.get("totals", {})
        expected_totals = ["total_rutas", "total_paquetes", "completados"]
        for field in expected_totals:
            assert field in totals, f"Missing total field {field}: {totals.keys()}"
        print(f"✓ Routes report totals structure correct: {totals}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
