"""
Iteration 19 - Admin IA Module Tests
Tests for:
- Admin summary endpoint
- Token usage endpoint with pagination
- Routes report endpoint with filters
- Routes report Excel export
- Config GET/PATCH endpoints
- Role-based access control
- Training samples endpoint with human_note and corrected_score
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEV_CREDS = {"email": "dev@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}  # developer role - full admin access
COORD_CREDS = {"email": "yael@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}  # coordinator role - NO admin access
AGENT_CREDS = {"email": "agente@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}  # agent role - NO admin access


@pytest.fixture(scope="module")
def dev_token():
    """Get developer token for admin access"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=DEV_CREDS)
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Developer login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def coord_token():
    """Get coordinator token (should NOT have admin access)"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=COORD_CREDS)
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Coordinator login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def agent_token():
    """Get agent token (should NOT have admin access)"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=AGENT_CREDS)
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Agent login failed: {response.status_code} - {response.text}")


@pytest.fixture
def dev_headers(dev_token):
    return {"Authorization": f"Bearer {dev_token}", "Content-Type": "application/json"}


@pytest.fixture
def coord_headers(coord_token):
    return {"Authorization": f"Bearer {coord_token}", "Content-Type": "application/json"}


@pytest.fixture
def agent_headers(agent_token):
    return {"Authorization": f"Bearer {agent_token}", "Content-Type": "application/json"}


# ==================== ADMIN SUMMARY TESTS ====================

class TestAdminSummary:
    """Tests for GET /api/admin/summary"""

    def test_summary_returns_200_for_developer(self, dev_headers):
        """Developer role should have access to admin summary"""
        response = requests.get(f"{BASE_URL}/api/admin/summary", headers=dev_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "by_entregable" in data, "Missing by_entregable in response"
        assert "totals" in data, "Missing totals in response"
        assert "evaluaciones_count" in data, "Missing evaluaciones_count"
        assert "lumi_count" in data, "Missing lumi_count"
        assert "reportes_count" in data, "Missing reportes_count"
        assert "over_budget" in data, "Missing over_budget flag"
        assert "budget_threshold" in data, "Missing budget_threshold"
        
        # Verify totals structure
        totals = data["totals"]
        assert "tokens_total" in totals
        assert "cost_usd" in totals
        assert "cost_mxn" in totals
        assert "input_pct" in totals
        assert "output_pct" in totals
        assert "prompt_pct" in totals
        print(f"Summary totals: {totals}")

    def test_summary_with_period_filter(self, dev_headers):
        """Test summary with period filter"""
        response = requests.get(
            f"{BASE_URL}/api/admin/summary",
            params={"period": "prev_month"},
            headers=dev_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "totals" in data
        print(f"Prev month summary: tokens={data['totals'].get('tokens_total', 0)}")

    def test_summary_denied_for_coordinator(self, coord_headers):
        """Coordinator role should NOT have admin access"""
        response = requests.get(f"{BASE_URL}/api/admin/summary", headers=coord_headers)
        assert response.status_code == 403, f"Expected 403 for coordinator, got {response.status_code}"
        print("Coordinator correctly denied admin access")

    def test_summary_denied_for_agent(self, agent_headers):
        """Agent role should NOT have admin access"""
        response = requests.get(f"{BASE_URL}/api/admin/summary", headers=agent_headers)
        assert response.status_code == 403, f"Expected 403 for agent, got {response.status_code}"
        print("Agent correctly denied admin access")


# ==================== TOKEN USAGE TESTS ====================

class TestTokenUsage:
    """Tests for GET /api/admin/token-usage"""

    def test_token_usage_returns_200(self, dev_headers):
        """Token usage endpoint should return paginated events"""
        response = requests.get(f"{BASE_URL}/api/admin/token-usage", headers=dev_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "summary" in data, "Missing summary"
        assert "events" in data, "Missing events"
        assert "pagination" in data, "Missing pagination"
        
        # Verify pagination structure
        pagination = data["pagination"]
        assert "total" in pagination
        assert "page" in pagination
        assert "page_size" in pagination
        assert "total_pages" in pagination
        
        # Verify summary structure
        summary = data["summary"]
        assert "by_entregable" in summary
        assert "totals" in summary
        
        print(f"Token usage: {pagination['total']} total events, page {pagination['page']}/{pagination['total_pages']}")

    def test_token_usage_with_filters(self, dev_headers):
        """Test token usage with entregable filter"""
        response = requests.get(
            f"{BASE_URL}/api/admin/token-usage",
            params={"entregable": "evaluacion", "page_size": 10},
            headers=dev_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # All events should be evaluacion type
        for event in data["events"]:
            assert event.get("entregable") == "evaluacion", f"Expected evaluacion, got {event.get('entregable')}"
        print(f"Filtered to evaluacion: {len(data['events'])} events")

    def test_token_usage_pagination(self, dev_headers):
        """Test pagination works correctly"""
        response = requests.get(
            f"{BASE_URL}/api/admin/token-usage",
            params={"page": 1, "page_size": 5},
            headers=dev_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) <= 5, "Page size not respected"
        print(f"Pagination working: {len(data['events'])} events on page 1")


# ==================== ROUTES REPORT TESTS ====================

class TestRoutesReport:
    """Tests for GET /api/admin/routes-report"""

    def test_routes_report_returns_200(self, dev_headers):
        """Routes report should return paginated route data"""
        response = requests.get(
            f"{BASE_URL}/api/admin/routes-report",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            headers=dev_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "totals" in data, "Missing totals"
        assert "rows" in data, "Missing rows"
        assert "pagination" in data, "Missing pagination"
        
        # Verify totals structure
        totals = data["totals"]
        assert "total_rutas" in totals
        assert "total_dias" in totals
        assert "total_paquetes" in totals
        assert "completados" in totals
        assert "con_evidencia" in totals
        assert "costo_total" in totals
        
        print(f"Routes report: {totals['total_rutas']} routes, {totals['total_paquetes']} packages")

    def test_routes_report_row_structure(self, dev_headers):
        """Verify route row has expected Cubbo ADM columns"""
        response = requests.get(
            f"{BASE_URL}/api/admin/routes-report",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31", "page_size": 1},
            headers=dev_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        if data["rows"]:
            row = data["rows"][0]
            expected_fields = [
                "order_id", "fecha", "driver", "team", "tipo_unidad", "estado",
                "proveedor", "costo", "pv", "asistencia_en_tiempo", "hora_entrada",
                "hora_salida", "horas_laboradas", "distancia_km", "total_paquetes",
                "completados", "con_evidencia", "score_ia", "journey_id"
            ]
            for field in expected_fields:
                assert field in row, f"Missing field: {field}"
            print(f"Row structure verified with {len(row)} fields")
        else:
            print("No routes found in date range (empty result is valid)")

    def test_routes_report_with_driver_filter(self, dev_headers):
        """Test routes report with driver filter"""
        response = requests.get(
            f"{BASE_URL}/api/admin/routes-report",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31", "driver": "Juan"},
            headers=dev_headers
        )
        assert response.status_code == 200
        print("Driver filter accepted")


# ==================== ROUTES REPORT EXCEL EXPORT TESTS ====================

class TestRoutesReportExport:
    """Tests for GET /api/admin/routes-report/export"""

    def test_export_returns_excel_file(self, dev_headers):
        """Export should return Excel file"""
        response = requests.get(
            f"{BASE_URL}/api/admin/routes-report/export",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            headers=dev_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify content type
        content_type = response.headers.get("content-type", "")
        assert "spreadsheet" in content_type or "excel" in content_type or "octet-stream" in content_type, \
            f"Expected Excel content type, got {content_type}"
        
        # Verify content disposition
        content_disp = response.headers.get("content-disposition", "")
        assert "LAYOUT_ADM_Cubbo" in content_disp, f"Expected Cubbo filename, got {content_disp}"
        assert ".xlsx" in content_disp, "Expected .xlsx extension"
        
        # Verify file has content
        assert len(response.content) > 0, "Excel file is empty"
        print(f"Excel export successful: {len(response.content)} bytes")

    def test_export_with_column_selection(self, dev_headers):
        """Export with specific columns"""
        response = requests.get(
            f"{BASE_URL}/api/admin/routes-report/export",
            params={
                "date_from": "2026-01-01",
                "date_to": "2026-12-31",
                "columns": "order_id,fecha,driver,score_ia"
            },
            headers=dev_headers
        )
        assert response.status_code == 200
        print("Column selection export successful")


# ==================== CONFIG TESTS ====================

class TestAdminConfig:
    """Tests for GET/PATCH /api/admin/config"""

    def test_config_get_returns_200(self, dev_headers):
        """Config GET should return all config sections"""
        response = requests.get(f"{BASE_URL}/api/admin/config", headers=dev_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify all config sections present
        assert "ia_cost_config" in data, "Missing ia_cost_config"
        assert "exchange_rate" in data, "Missing exchange_rate"
        assert "budget_alerts" in data, "Missing budget_alerts"
        
        # Verify exchange_rate structure
        er = data["exchange_rate"]
        assert "rate" in er, "Missing rate in exchange_rate"
        assert isinstance(er["rate"], (int, float)), "Rate should be numeric"
        
        # Verify budget_alerts structure
        ba = data["budget_alerts"]
        assert "monthly_threshold_usd" in ba, "Missing monthly_threshold_usd"
        assert "alert_enabled" in ba, "Missing alert_enabled"
        
        print(f"Config loaded: TC={er['rate']}, threshold=${ba['monthly_threshold_usd']}")

    def test_config_patch_exchange_rate(self, dev_headers):
        """Developer can update exchange rate"""
        # First get current value
        get_response = requests.get(f"{BASE_URL}/api/admin/config", headers=dev_headers)
        original_rate = get_response.json()["exchange_rate"]["rate"]
        
        # Update to new value
        new_rate = 19.50
        response = requests.patch(
            f"{BASE_URL}/api/admin/config",
            json={"section": "exchange_rate", "value": {"rate": new_rate, "source": "manual", "auto_update": False}},
            headers=dev_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify update
        verify_response = requests.get(f"{BASE_URL}/api/admin/config", headers=dev_headers)
        updated_rate = verify_response.json()["exchange_rate"]["rate"]
        assert updated_rate == new_rate, f"Rate not updated: expected {new_rate}, got {updated_rate}"
        
        # Restore original
        requests.patch(
            f"{BASE_URL}/api/admin/config",
            json={"section": "exchange_rate", "value": {"rate": original_rate, "source": "manual", "auto_update": False}},
            headers=dev_headers
        )
        print(f"Exchange rate update verified: {original_rate} -> {new_rate} -> {original_rate}")

    def test_config_patch_budget_alerts(self, dev_headers):
        """Developer can update budget alerts"""
        response = requests.patch(
            f"{BASE_URL}/api/admin/config",
            json={
                "section": "budget_alerts",
                "value": {"monthly_threshold_usd": 100, "alert_enabled": True, "weekly_report_enabled": False}
            },
            headers=dev_headers
        )
        assert response.status_code == 200
        print("Budget alerts update successful")

    def test_config_patch_invalid_section(self, dev_headers):
        """Invalid section should return 400"""
        response = requests.patch(
            f"{BASE_URL}/api/admin/config",
            json={"section": "invalid_section", "value": {}},
            headers=dev_headers
        )
        assert response.status_code == 400, f"Expected 400 for invalid section, got {response.status_code}"
        print("Invalid section correctly rejected")

    def test_config_patch_denied_for_coordinator(self, coord_headers):
        """Coordinator cannot edit config (only developer can)"""
        response = requests.patch(
            f"{BASE_URL}/api/admin/config",
            json={"section": "exchange_rate", "value": {"rate": 20.0}},
            headers=coord_headers
        )
        assert response.status_code == 403, f"Expected 403 for coordinator edit, got {response.status_code}"
        print("Coordinator correctly denied config edit")


# ==================== TRAINING SAMPLES TESTS ====================

class TestTrainingSamples:
    """Tests for POST /api/training/samples with human_note and corrected_score"""

    def test_training_samples_accepts_human_note(self, dev_headers):
        """Training samples should accept human_note field"""
        # First get a journey with packages
        journeys_response = requests.get(f"{BASE_URL}/api/journeys", headers=dev_headers)
        if journeys_response.status_code != 200:
            pytest.skip("Could not fetch journeys")
        
        journeys_data = journeys_response.json()
        journeys = journeys_data.get("data", journeys_data) if isinstance(journeys_data, dict) else journeys_data
        if not journeys:
            pytest.skip("No journeys available for testing")
        
        journey_id = journeys[0]["id"]
        
        # Get packages for this journey
        packages_response = requests.get(
            f"{BASE_URL}/api/journeys/{journey_id}/packages-quality",
            headers=dev_headers
        )
        if packages_response.status_code != 200:
            pytest.skip("Could not fetch packages")
        
        packages = packages_response.json().get("packages", [])
        if not packages:
            pytest.skip("No packages available for testing")
        
        guide = packages[0].get("guide", packages[0].get("tracking_number", "TEST-GUIDE"))
        
        # Submit training sample with human_note and corrected_score
        response = requests.post(
            f"{BASE_URL}/api/training/samples",
            json={
                "journey_id": journey_id,
                "guide": guide,
                "human_label": "correct",
                "human_note": "Test note for supervised training",
                "corrected_score": 95
            },
            headers=dev_headers
        )
        
        # Accept 200, 201, or 409 (duplicate)
        assert response.status_code in [200, 201, 409], \
            f"Expected 200/201/409, got {response.status_code}: {response.text}"
        print(f"Training sample submission: {response.status_code}")

    def test_training_samples_validation(self, dev_headers):
        """Training samples should validate required fields"""
        response = requests.post(
            f"{BASE_URL}/api/training/samples",
            json={"journey_id": "test", "guide": "test"},  # Missing label
            headers=dev_headers
        )
        # Should fail validation
        assert response.status_code in [400, 422], \
            f"Expected validation error, got {response.status_code}"
        print("Training samples validation working")


# ==================== ROLE-BASED ACCESS CONTROL TESTS ====================

class TestRoleBasedAccess:
    """Comprehensive RBAC tests for admin module"""

    def test_all_admin_endpoints_require_auth(self):
        """All admin endpoints should require authentication"""
        endpoints = [
            "/api/admin/summary",
            "/api/admin/token-usage",
            "/api/admin/routes-report?date_from=2026-01-01&date_to=2026-12-31",
            "/api/admin/config"
        ]
        
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}{endpoint}")
            assert response.status_code in [401, 403], \
                f"Endpoint {endpoint} should require auth, got {response.status_code}"
        print("All admin endpoints require authentication")

    def test_developer_has_full_access(self, dev_headers):
        """Developer role should have full admin access"""
        endpoints = [
            ("GET", "/api/admin/summary"),
            ("GET", "/api/admin/token-usage"),
            ("GET", "/api/admin/routes-report?date_from=2026-01-01&date_to=2026-12-31"),
            ("GET", "/api/admin/config"),
        ]
        
        for method, endpoint in endpoints:
            if method == "GET":
                response = requests.get(f"{BASE_URL}{endpoint}", headers=dev_headers)
            assert response.status_code == 200, \
                f"Developer should access {endpoint}, got {response.status_code}"
        print("Developer has full admin access")

    def test_coordinator_denied_admin_access(self, coord_headers):
        """Coordinator role should be denied admin access"""
        response = requests.get(f"{BASE_URL}/api/admin/summary", headers=coord_headers)
        assert response.status_code == 403
        
        response = requests.get(f"{BASE_URL}/api/admin/token-usage", headers=coord_headers)
        assert response.status_code == 403
        print("Coordinator correctly denied all admin endpoints")

    def test_agent_denied_admin_access(self, agent_headers):
        """Agent role should be denied admin access"""
        response = requests.get(f"{BASE_URL}/api/admin/summary", headers=agent_headers)
        assert response.status_code == 403
        
        response = requests.get(f"{BASE_URL}/api/admin/token-usage", headers=agent_headers)
        assert response.status_code == 403
        print("Agent correctly denied all admin endpoints")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
