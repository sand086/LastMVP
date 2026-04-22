"""
Iteration 18 Tests - Quality Tab V2, Quality Criteria, API Documentation
Tests for:
1. Quality Criteria page (5 tabs: Evidencias, KPIs, SLA, Config IA, Tipos de Error)
2. Quality Tab V2 in Journey Detail (KPI strip, distribution bar, error summary, package table)
3. New API endpoints: quality-summary, packages-quality, training/samples, package review
4. API Documentation schema includes all new v2 endpoints
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEV_EMAIL = "dev@me.mx"
DEV_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
COORD_EMAIL = "yael@me.mx"
COORD_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")


class TestAuth:
    """Authentication tests"""
    
    def test_login_developer(self):
        """Test developer login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEV_EMAIL,
            "password": DEV_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        assert "user" in data, "No user in response"
        assert data["user"]["role"] == "developer"
        print(f"✓ Developer login successful: {data['user']['email']}")
        return data["access_token"]
    
    def test_login_coordinator(self):
        """Test coordinator login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORD_EMAIL,
            "password": COORD_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "coordinator"
        print(f"✓ Coordinator login successful: {data['user']['email']}")
        return data["access_token"]


@pytest.fixture(scope="module")
def dev_token():
    """Get developer auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEV_EMAIL,
        "password": DEV_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip("Developer login failed")
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def coord_token():
    """Get coordinator auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": COORD_EMAIL,
        "password": COORD_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip("Coordinator login failed")
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(dev_token):
    """Auth headers for requests"""
    return {"Authorization": f"Bearer {dev_token}"}


@pytest.fixture(scope="module")
def sample_journey_id(auth_headers):
    """Get a sample journey ID for testing"""
    response = requests.get(f"{BASE_URL}/api/journeys", headers=auth_headers)
    if response.status_code != 200:
        pytest.skip("Could not fetch journeys")
    data = response.json()
    # Handle both {"data": [...]} and [...] formats
    journeys = data.get("data", data) if isinstance(data, dict) else data
    if not journeys:
        pytest.skip("No journeys available for testing")
    # Prefer closed journeys for quality testing
    closed = [j for j in journeys if isinstance(j, dict) and j.get("status") == "closed"]
    if closed:
        return closed[0]["id"]
    # Return first journey if no closed ones
    if isinstance(journeys[0], dict):
        return journeys[0]["id"]
    pytest.skip("Invalid journey data format")


class TestQualityCriteriaAPI:
    """Tests for Quality Criteria settings API"""
    
    def test_get_quality_criteria(self, auth_headers):
        """GET /api/quality/criteria - Get quality criteria config"""
        response = requests.get(f"{BASE_URL}/api/quality/criteria", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "delivery_types" in data, "Missing delivery_types"
        assert "third_party_keywords" in data, "Missing third_party_keywords"
        
        # Verify delivery types
        assert "exitosa" in data["delivery_types"], "Missing exitosa delivery type"
        assert "terceros" in data["delivery_types"], "Missing terceros delivery type"
        assert "fallida" in data["delivery_types"], "Missing fallida delivery type"
        
        # Verify exitosa has required_evidence
        exitosa = data["delivery_types"]["exitosa"]
        assert "required_evidence" in exitosa, "Missing required_evidence in exitosa"
        assert len(exitosa["required_evidence"]) >= 3, "Should have at least 3 evidence items"
        
        print(f"✓ Quality criteria loaded: {len(data['delivery_types'])} delivery types")
    
    def test_get_quality_settings(self, auth_headers):
        """GET /api/config/quality-settings - Get all quality settings (5 tabs)"""
        response = requests.get(f"{BASE_URL}/api/config/quality-settings", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify all 5 tab sections are present
        assert "kpi_targets" in data, "Missing kpi_targets (KPIs tab)"
        assert "sla_brackets" in data, "Missing sla_brackets (SLA tab)"
        assert "sla_targets_by_rubro" in data, "Missing sla_targets_by_rubro (SLA tab)"
        assert "penalty_rules" in data, "Missing penalty_rules (SLA tab)"
        assert "strike_policy" in data, "Missing strike_policy (SLA tab)"
        assert "ia_config" in data, "Missing ia_config (Config IA tab)"
        assert "error_catalog" in data, "Missing error_catalog (Tipos de Error tab)"
        assert "_meta" in data, "Missing _meta version info"
        
        # Verify KPI targets structure
        kpi = data["kpi_targets"]
        assert "score_min_acceptable" in kpi, "Missing score_min_acceptable"
        assert "score_target" in kpi, "Missing score_target"
        assert "score_excellent" in kpi, "Missing score_excellent"
        assert "weights" in kpi, "Missing weights"
        
        # Verify IA config structure
        ia = data["ia_config"]
        assert "provider" in ia, "Missing provider in ia_config"
        assert "model" in ia, "Missing model in ia_config"
        assert "enabled" in ia, "Missing enabled in ia_config"
        
        # Verify error catalog
        errors = data["error_catalog"]
        assert isinstance(errors, list), "error_catalog should be a list"
        assert len(errors) >= 5, "Should have at least 5 error types"
        
        print(f"✓ Quality settings loaded: {len(errors)} error types, KPI target: {kpi.get('score_target')}%")
    
    def test_patch_quality_settings_kpi(self, auth_headers):
        """PATCH /api/config/quality-settings - Update KPI targets"""
        # First get current values
        response = requests.get(f"{BASE_URL}/api/config/quality-settings", headers=auth_headers)
        current = response.json()
        original_target = current["kpi_targets"]["score_target"]
        
        # Update KPI targets
        new_kpi = {
            **current["kpi_targets"],
            "score_target": 92  # Change target
        }
        
        response = requests.patch(
            f"{BASE_URL}/api/config/quality-settings",
            headers=auth_headers,
            json={"section": "kpi_targets", "value": new_kpi}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["success"]
        assert data["section"] == "kpi_targets"
        
        # Verify change persisted
        response = requests.get(f"{BASE_URL}/api/config/quality-settings", headers=auth_headers)
        updated = response.json()
        assert updated["kpi_targets"]["score_target"] == 92
        
        # Restore original
        new_kpi["score_target"] = original_target
        requests.patch(
            f"{BASE_URL}/api/config/quality-settings",
            headers=auth_headers,
            json={"section": "kpi_targets", "value": new_kpi}
        )
        
        print("✓ KPI targets update and restore successful")


class TestQualityTabV2API:
    """Tests for Quality Tab V2 endpoints"""
    
    def test_get_quality_summary(self, auth_headers, sample_journey_id):
        """GET /api/journeys/{journey_id}/quality-summary - KPI strip data"""
        response = requests.get(
            f"{BASE_URL}/api/journeys/{sample_journey_id}/quality-summary",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify KPI strip fields
        assert "score_avg" in data, "Missing score_avg"
        assert "score_target" in data, "Missing score_target"
        assert "distribution" in data, "Missing distribution"
        assert "evaluated_ia" in data, "Missing evaluated_ia"
        assert "total" in data, "Missing total"
        assert "confidence_avg" in data, "Missing confidence_avg"
        assert "reviewed_count" in data, "Missing reviewed_count"
        
        # Verify distribution structure
        dist = data["distribution"]
        assert "complete" in dist, "Missing complete in distribution"
        assert "partial" in dist, "Missing partial in distribution"
        assert "incomplete" in dist, "Missing incomplete in distribution"
        assert "complete_pct" in dist, "Missing complete_pct"
        assert "partial_pct" in dist, "Missing partial_pct"
        assert "incomplete_pct" in dist, "Missing incomplete_pct"
        
        # Verify error_summary if present
        if "error_summary" in data and data["error_summary"]:
            for err in data["error_summary"]:
                assert "key" in err, "Missing key in error_summary item"
                assert "label" in err, "Missing label in error_summary item"
                assert "count" in err, "Missing count in error_summary item"
        
        print(f"✓ Quality summary: score_avg={data['score_avg']}%, total={data['total']}, evaluated_ia={data['evaluated_ia']}")
    
    def test_get_packages_quality(self, auth_headers, sample_journey_id):
        """GET /api/journeys/{journey_id}/packages-quality - Package table data"""
        response = requests.get(
            f"{BASE_URL}/api/journeys/{sample_journey_id}/packages-quality",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify pagination structure
        assert "packages" in data, "Missing packages"
        assert "total" in data, "Missing total"
        assert "page" in data, "Missing page"
        assert "page_size" in data, "Missing page_size"
        assert "pages" in data, "Missing pages"
        
        # Verify package fields if packages exist
        if data["packages"]:
            pkg = data["packages"][0]
            expected_fields = [
                "id", "guide", "delivery_type", "status",
                "ia_score", "ia_confidence", "ia_errors", "ia_severity",
                "attempt_number", "review_status", "photo_count"
            ]
            for field in expected_fields:
                assert field in pkg, f"Missing {field} in package"
            
            print(f"✓ Packages quality: {len(data['packages'])} packages, total={data['total']}")
        else:
            print("✓ Packages quality endpoint works (no packages with quality data)")
    
    def test_get_packages_quality_alerts_only(self, auth_headers, sample_journey_id):
        """GET /api/journeys/{journey_id}/packages-quality?alerts_only=true"""
        response = requests.get(
            f"{BASE_URL}/api/journeys/{sample_journey_id}/packages-quality",
            headers=auth_headers,
            params={"alerts_only": True}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "packages" in data
        print(f"✓ Packages quality (alerts_only): {len(data['packages'])} packages with alerts")
    
    def test_get_packages_quality_pagination(self, auth_headers, sample_journey_id):
        """GET /api/journeys/{journey_id}/packages-quality with pagination"""
        response = requests.get(
            f"{BASE_URL}/api/journeys/{sample_journey_id}/packages-quality",
            headers=auth_headers,
            params={"page": 1, "page_size": 10}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["page"] == 1
        assert data["page_size"] == 10
        assert len(data["packages"]) <= 10
        print(f"✓ Packages quality pagination works: page={data['page']}, pages={data['pages']}")


class TestTrainingSamplesAPI:
    """Tests for training samples endpoint"""
    
    def test_training_samples_requires_auth(self):
        """POST /api/training/samples requires authentication"""
        response = requests.post(f"{BASE_URL}/api/training/samples", json={})
        assert response.status_code == 401 or response.status_code == 403
        print("✓ Training samples endpoint requires authentication")
    
    def test_training_samples_validation(self, auth_headers):
        """POST /api/training/samples validates required fields"""
        response = requests.post(
            f"{BASE_URL}/api/training/samples",
            headers=auth_headers,
            json={"journey_id": "test"}  # Missing required fields
        )
        # Should fail validation (400) or supervised training disabled (400)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("✓ Training samples validates required fields")


class TestPackageReviewAPI:
    """Tests for package review endpoint"""
    
    def test_package_review_validation(self, auth_headers, sample_journey_id):
        """PATCH /api/journeys/{journey_id}/packages/{guide}/review validates status"""
        response = requests.patch(
            f"{BASE_URL}/api/journeys/{sample_journey_id}/packages/INVALID_GUIDE/review",
            headers=auth_headers,
            json={"review_status": "invalid_status"}
        )
        # Should fail validation
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Package review validates review_status")


class TestAPIDocumentation:
    """Tests for API Documentation schema"""
    
    def test_get_report_schema(self, auth_headers):
        """GET /api/reports/schema - Verify all v2 endpoints are documented"""
        response = requests.get(f"{BASE_URL}/api/reports/schema", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "api_version" in data, "Missing api_version"
        assert "endpoints" in data, "Missing endpoints"
        
        endpoints = data["endpoints"]
        endpoint_paths = [e["endpoint"] for e in endpoints]
        
        # Verify new v2 endpoints are documented
        v2_endpoints = [
            "/api/journeys/{journey_id}/quality-summary",
            "/api/journeys/{journey_id}/packages-quality",
            "/api/training/samples",
            "/api/journeys/{journey_id}/packages/{guide}/review",
        ]
        
        for ep in v2_endpoints:
            assert ep in endpoint_paths, f"Missing endpoint in schema: {ep}"
        
        print(f"✓ API schema includes all {len(v2_endpoints)} new v2 endpoints")
        print(f"  Total documented endpoints: {len(endpoints)}")
    
    def test_schema_endpoint_details(self, auth_headers):
        """Verify schema endpoint details are complete"""
        response = requests.get(f"{BASE_URL}/api/reports/schema", headers=auth_headers)
        data = response.json()
        
        for endpoint in data["endpoints"]:
            assert "name" in endpoint, "Missing name in endpoint"
            assert "endpoint" in endpoint, "Missing endpoint path"
            assert "method" in endpoint, f"Missing method in {endpoint.get('name')}"
            assert "description" in endpoint, f"Missing description in {endpoint.get('name')}"
        
        print("✓ All schema endpoints have required fields (name, endpoint, method, description)")


class TestBackendIndexes:
    """Tests to verify backend performance indexes are working"""
    
    def test_journeys_query_performance(self, auth_headers):
        """Verify journeys query works (indexes should be in place)"""
        response = requests.get(
            f"{BASE_URL}/api/journeys",
            headers=auth_headers,
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        print("✓ Journeys query with date filter works")
    
    def test_packages_quality_query_performance(self, auth_headers, sample_journey_id):
        """Verify packages quality query works (indexes should be in place)"""
        response = requests.get(
            f"{BASE_URL}/api/journeys/{sample_journey_id}/packages-quality",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        print("✓ Packages quality query works")


class TestHealthAndBasics:
    """Basic health checks"""
    
    def test_health_endpoint(self):
        """GET /api/health"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("✓ Health endpoint OK")
    
    def test_root_endpoint(self):
        """GET /api/"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "LastMile OS API" in data.get("message", "")
        print("✓ Root endpoint OK")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
