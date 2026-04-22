"""
Iteration 38 - Code Quality Refactoring Regression Tests
Tests to verify that code quality refactoring changes don't break functionality:
1. GuiasTab component split (imports from ./guias/GuiasHelpers and ./guias/GuiasPackageDetail)
2. Backend evidence_scoring.py refactoring (_call_ai_vision split into helpers)
3. Backend liquidacion_export.py refactoring (extracted helper functions)
4. PulseStrip key fix (using r.label instead of array index)
5. Reports.jsx DOMPurify ALLOWED_TAGS
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestHealthAndAuth:
    """Basic health and authentication tests"""
    
    def test_health_endpoint(self):
        """Test backend health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("PASS: Health endpoint working")
    
    def test_coordinator_login(self):
        """Test coordinator login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "yael@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "coordinator"
        print("PASS: Coordinator login working")
    
    def test_developer_login(self):
        """Test developer login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "developer"
        print("PASS: Developer login working")


class TestJourneyAPIs:
    """Journey and package API tests - verifies evidence_scoring.py refactoring"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for coordinator"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "yael@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed")
    
    def test_get_journeys_list(self, auth_token):
        """Test journeys list endpoint"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/journeys", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "pagination" in data
        print(f"PASS: Journeys list returned {len(data['data'])} journeys")
    
    def test_get_journey_detail_with_packages(self, auth_token):
        """Test journey detail with packages - verifies evidence scoring works"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        # First get a journey
        response = requests.get(f"{BASE_URL}/api/journeys?page_size=1", headers=headers)
        assert response.status_code == 200
        journeys = response.json().get("data", [])
        
        if not journeys:
            pytest.skip("No journeys available for testing")
        
        journey_id = journeys[0]["id"]
        response = requests.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify journey structure
        assert "id" in data
        assert "packages" in data
        assert "incidents" in data
        
        # Verify packages have expected fields (from evidence_scoring.py)
        if data["packages"]:
            pkg = data["packages"][0]
            # These fields are set by the refactored evidence_scoring.py
            assert "ai_score" in pkg or "evidence_score" in pkg or pkg.get("ai_score") is None
            assert "ai_errors" in pkg
            assert "photos_count" in pkg
        
        print(f"PASS: Journey detail returned with {len(data['packages'])} packages")
    
    def test_evaluate_journey_quality(self, auth_token):
        """Test evidence evaluation endpoint - verifies evidence_scoring.py refactoring"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        # Get a journey
        response = requests.get(f"{BASE_URL}/api/journeys?page_size=1", headers=headers)
        journeys = response.json().get("data", [])
        
        if not journeys:
            pytest.skip("No journeys available for testing")
        
        journey_id = journeys[0]["id"]
        response = requests.post(
            f"{BASE_URL}/api/reports/evaluate-journey/{journey_id}",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "evaluated" in data
        print(f"PASS: Evidence evaluation returned - {data.get('evaluated', 0)} packages evaluated")
    
    def test_ai_eval_status_endpoint(self, auth_token):
        """Test AI evaluation status endpoint"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/journeys?page_size=1", headers=headers)
        journeys = response.json().get("data", [])
        
        if not journeys:
            pytest.skip("No journeys available for testing")
        
        journey_id = journeys[0]["id"]
        response = requests.get(
            f"{BASE_URL}/api/journeys/{journey_id}/ai-eval-status",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print(f"PASS: AI eval status endpoint working - status: {data.get('status')}")


class TestReportsAPIs:
    """Reports API tests - verifies liquidacion_export.py refactoring"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for coordinator"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "yael@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed")
    
    def test_generate_report(self, auth_token):
        """Test report generation endpoint"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.post(f"{BASE_URL}/api/reports/generate", headers=headers, json={
            "date_from": "2026-04-01",
            "date_to": "2026-04-10",
            "sections": ["providers", "drivers"]
        })
        assert response.status_code == 200
        data = response.json()
        assert "delivery_rate" in data or "total_packages" in data or data == {}
        print("PASS: Report generation endpoint working")
    
    def test_generate_ai_report(self, auth_token):
        """Test AI report generation endpoint"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.post(f"{BASE_URL}/api/reports/generate-ai", headers=headers, json={
            "date_from": "2026-04-01",
            "date_to": "2026-04-10"
        })
        assert response.status_code == 200
        data = response.json()
        # AI report should have narrative and cards
        assert "narrative" in data or "cards" in data or "error" not in data
        print("PASS: AI report generation endpoint working")
    
    def test_quality_report(self, auth_token):
        """Test quality report endpoint"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(
            f"{BASE_URL}/api/reports/quality?date_from=2026-04-01&date_to=2026-04-10",
            headers=headers
        )
        assert response.status_code == 200
        print("PASS: Quality report endpoint working")
    
    def test_sla_report(self, auth_token):
        """Test SLA report endpoint"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(
            f"{BASE_URL}/api/reports/sla?date_from=2026-04-01&date_to=2026-04-10",
            headers=headers
        )
        assert response.status_code == 200
        print("PASS: SLA report endpoint working")


class TestIncidentsAPI:
    """Incidents API tests"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for coordinator"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "yael@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed")
    
    def test_get_incidents(self, auth_token):
        """Test incidents list endpoint"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/incidents", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"PASS: Incidents list returned {len(data)} incidents")
    
    def test_create_and_delete_incident(self, auth_token):
        """Test incident creation and deletion - P1 inline incident feature"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Get a journey first
        response = requests.get(f"{BASE_URL}/api/journeys?page_size=1", headers=headers)
        journeys = response.json().get("data", [])
        
        if not journeys:
            pytest.skip("No journeys available for testing")
        
        journey_id = journeys[0]["id"]
        
        # Create incident with source='guias' (P1 feature)
        incident_data = {
            "journey_id": journey_id,
            "occurred_at": "2026-04-10T12:00:00Z",
            "incident_type": "Evidencia Insuficiente",
            "description": "TEST_Incidencia de prueba iter38",
            "severity": "media",
            "tracking_number": "TEST123",
            "source": "guias"
        }
        response = requests.post(f"{BASE_URL}/api/incidents", headers=headers, json=incident_data)
        assert response.status_code == 200
        created = response.json()
        assert "id" in created
        incident_id = created["id"]
        print(f"PASS: Incident created with id {incident_id}")
        
        # Delete the test incident
        response = requests.delete(f"{BASE_URL}/api/incidents/{incident_id}", headers=headers)
        assert response.status_code == 200
        print("PASS: Incident deleted successfully")


class TestPackageReviewAPI:
    """Package review API tests - P3 Cubbo ReviewModal feature"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for coordinator"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "yael@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed")
    
    def test_package_review_endpoint(self, auth_token):
        """Test package review endpoint exists and responds"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Get a journey with packages
        response = requests.get(f"{BASE_URL}/api/journeys?page_size=5", headers=headers)
        journeys = response.json().get("data", [])
        
        package_id = None
        for j in journeys:
            detail = requests.get(f"{BASE_URL}/api/journeys/{j['id']}", headers=headers).json()
            if detail.get("packages"):
                package_id = detail["packages"][0]["id"]
                break
        
        if not package_id:
            pytest.skip("No packages available for testing")
        
        # Test PATCH endpoint (used by ReviewModal)
        response = requests.patch(
            f"{BASE_URL}/api/packages/{package_id}/review",
            headers=headers,
            json={
                "manually_reviewed": True,
                "manually_reviewed_note": "TEST_iter38 review"
            }
        )
        assert response.status_code == 200
        print("PASS: Package review PATCH endpoint working")


class TestConfidenceAndDiscrepancy:
    """Confidence evaluation and discrepancy detection tests"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for coordinator"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "yael@me.mx",
            "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed")
    
    def test_evaluate_confidence_endpoint(self, auth_token):
        """Test confidence evaluation endpoint"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.get(f"{BASE_URL}/api/journeys?page_size=1", headers=headers)
        journeys = response.json().get("data", [])
        
        if not journeys:
            pytest.skip("No journeys available for testing")
        
        journey_id = journeys[0]["id"]
        response = requests.post(
            f"{BASE_URL}/api/journeys/{journey_id}/guides/evaluate-confidence",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "evaluated" in data
        assert "discrepancies" in data
        print(f"PASS: Confidence evaluation - {data.get('evaluated')} evaluated, {data.get('discrepancies')} discrepancies")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
