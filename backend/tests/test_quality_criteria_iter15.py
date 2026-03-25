"""
Test Quality Criteria Endpoints - Iteration 15
Tests for:
1. GET /api/quality/criteria - Returns criteria with delivery_types
2. PUT /api/quality/criteria - Updates criteria (test updating third_party_keywords)
3. POST /api/quality/criteria/reset - Resets to defaults
4. Role-based access: Agent role should get 403
5. GET /api/reports/schema - Should return 17 endpoints
6. All major endpoints still work after refactoring
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestQualityCriteriaEndpoints:
    """Quality criteria CRUD tests for Coordinator/Developer roles"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as developer before each test"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as developer
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": "LastMile2026"
        })
        assert login_res.status_code == 200, f"Developer login failed: {login_res.text}"
        self.dev_token = login_res.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.dev_token}"})
        yield
        # Cleanup
        self.session.close()
    
    def test_get_quality_criteria_returns_delivery_types(self):
        """GET /api/quality/criteria should return criteria with 3 delivery_types"""
        res = self.session.get(f"{BASE_URL}/api/quality/criteria")
        assert res.status_code == 200, f"Failed to get criteria: {res.text}"
        
        data = res.json()
        assert "delivery_types" in data, "Response missing delivery_types"
        assert "third_party_keywords" in data, "Response missing third_party_keywords"
        
        # Verify 3 delivery types exist
        delivery_types = data["delivery_types"]
        assert "exitosa" in delivery_types, "Missing 'exitosa' delivery type"
        assert "terceros" in delivery_types, "Missing 'terceros' delivery type"
        assert "fallida" in delivery_types, "Missing 'fallida' delivery type"
        
        # Verify exitosa has required_evidence
        exitosa = delivery_types["exitosa"]
        assert "required_evidence" in exitosa, "exitosa missing required_evidence"
        assert "scoring_rules" in exitosa, "exitosa missing scoring_rules"
        assert len(exitosa["required_evidence"]) >= 3, "exitosa should have at least 3 evidence items"
        
        print(f"✓ Quality criteria returned with {len(delivery_types)} delivery types")
    
    def test_update_quality_criteria_third_party_keywords(self):
        """PUT /api/quality/criteria should update third_party_keywords"""
        # First get current criteria
        get_res = self.session.get(f"{BASE_URL}/api/quality/criteria")
        assert get_res.status_code == 200
        original_keywords = get_res.json().get("third_party_keywords", [])
        
        # Update with new keywords
        new_keywords = ["vecino", "vigilante", "tercero", "familiar", "portero", "TEST_KEYWORD"]
        update_res = self.session.put(f"{BASE_URL}/api/quality/criteria", json={
            "third_party_keywords": new_keywords
        })
        assert update_res.status_code == 200, f"Failed to update criteria: {update_res.text}"
        
        # Verify update response
        update_data = update_res.json()
        assert "message" in update_data, "Update response missing message"
        assert "version" in update_data, "Update response missing version"
        
        # Verify persistence with GET
        verify_res = self.session.get(f"{BASE_URL}/api/quality/criteria")
        assert verify_res.status_code == 200
        verify_data = verify_res.json()
        assert "TEST_KEYWORD" in verify_data.get("third_party_keywords", []), "Keyword update not persisted"
        
        # Cleanup: restore original keywords (without TEST_KEYWORD)
        restore_keywords = [kw for kw in new_keywords if kw != "TEST_KEYWORD"]
        self.session.put(f"{BASE_URL}/api/quality/criteria", json={
            "third_party_keywords": restore_keywords
        })
        
        print("✓ Quality criteria third_party_keywords updated and persisted")
    
    def test_reset_quality_criteria(self):
        """POST /api/quality/criteria/reset should reset to defaults"""
        res = self.session.post(f"{BASE_URL}/api/quality/criteria/reset")
        assert res.status_code == 200, f"Failed to reset criteria: {res.text}"
        
        data = res.json()
        assert "message" in data, "Reset response missing message"
        assert "criteria" in data, "Reset response missing criteria"
        
        # Verify reset criteria has default structure
        criteria = data["criteria"]
        assert "delivery_types" in criteria
        assert "third_party_keywords" in criteria
        assert criteria["version"] == 1, "Reset should set version to 1"
        
        print("✓ Quality criteria reset to defaults successfully")


class TestQualityCriteriaRoleAccess:
    """Test role-based access control for quality criteria"""
    
    def test_agent_gets_403_on_quality_criteria(self):
        """Agent role should get 403 Forbidden on quality criteria endpoints"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        # Login as agent
        login_res = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "agente@me.mx",
            "password": "LastMile2026"
        })
        assert login_res.status_code == 200, f"Agent login failed: {login_res.text}"
        agent_token = login_res.json().get("access_token")
        session.headers.update({"Authorization": f"Bearer {agent_token}"})
        
        # Try to GET quality criteria - should get 403
        get_res = session.get(f"{BASE_URL}/api/quality/criteria")
        assert get_res.status_code == 403, f"Expected 403 for agent, got {get_res.status_code}"
        
        # Try to PUT quality criteria - should get 403
        put_res = session.put(f"{BASE_URL}/api/quality/criteria", json={
            "third_party_keywords": ["test"]
        })
        assert put_res.status_code == 403, f"Expected 403 for agent PUT, got {put_res.status_code}"
        
        # Try to POST reset - should get 403
        reset_res = session.post(f"{BASE_URL}/api/quality/criteria/reset")
        assert reset_res.status_code == 403, f"Expected 403 for agent reset, got {reset_res.status_code}"
        
        session.close()
        print("✓ Agent role correctly gets 403 on all quality criteria endpoints")
    
    def test_coordinator_can_access_quality_criteria(self):
        """Coordinator role should have access to quality criteria"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        # Login as coordinator
        login_res = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "yael@me.mx",
            "password": "LastMile2026"
        })
        assert login_res.status_code == 200, f"Coordinator login failed: {login_res.text}"
        coord_token = login_res.json().get("access_token")
        session.headers.update({"Authorization": f"Bearer {coord_token}"})
        
        # GET quality criteria - should succeed
        get_res = session.get(f"{BASE_URL}/api/quality/criteria")
        assert get_res.status_code == 200, f"Coordinator should access criteria, got {get_res.status_code}"
        
        session.close()
        print("✓ Coordinator role can access quality criteria")


class TestReportsSchemaEndpoint:
    """Test that reports/schema returns expected number of endpoints"""
    
    def test_reports_schema_returns_17_endpoints(self):
        """GET /api/reports/schema should return 17 endpoints"""
        session = requests.Session()
        session.headers.update({"Content-Type": "application/json"})
        
        # Login as developer
        login_res = session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": "LastMile2026"
        })
        assert login_res.status_code == 200
        token = login_res.json().get("access_token")
        session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Get schema
        res = session.get(f"{BASE_URL}/api/reports/schema")
        assert res.status_code == 200, f"Failed to get schema: {res.text}"
        
        data = res.json()
        assert "endpoints" in data, "Schema missing endpoints"
        
        endpoints = data["endpoints"]
        endpoint_count = len(endpoints)
        
        # Should have 17 endpoints as per requirements
        assert endpoint_count >= 17, f"Expected at least 17 endpoints, got {endpoint_count}"
        
        # Print endpoint names for verification
        print(f"✓ Reports schema returned {endpoint_count} endpoints:")
        for ep in endpoints[:5]:
            print(f"  - {ep.get('method', 'GET')} {ep.get('path', ep.get('endpoint', 'unknown'))}")
        if endpoint_count > 5:
            print(f"  ... and {endpoint_count - 5} more")
        
        session.close()


class TestMajorEndpointsAfterRefactoring:
    """Verify all major endpoints still work after server.py refactoring"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login as developer"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_res = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": "LastMile2026"
        })
        assert login_res.status_code == 200
        self.token = login_res.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        yield
        self.session.close()
    
    def test_journeys_endpoint(self):
        """GET /api/journeys should work"""
        res = self.session.get(f"{BASE_URL}/api/journeys")
        assert res.status_code == 200, f"Journeys failed: {res.text}"
        data = res.json()
        assert "data" in data or isinstance(data, list), "Invalid journeys response"
        print("✓ Journeys endpoint working")
    
    def test_packages_search_endpoint(self):
        """GET /api/packages/search should work"""
        res = self.session.get(f"{BASE_URL}/api/packages/search?q=test")
        assert res.status_code == 200, f"Package search failed: {res.text}"
        print("✓ Package search endpoint working")
    
    def test_incidents_endpoint(self):
        """GET /api/incidents should work"""
        res = self.session.get(f"{BASE_URL}/api/incidents")
        assert res.status_code == 200, f"Incidents failed: {res.text}"
        print("✓ Incidents endpoint working")
    
    def test_dashboard_stats_endpoint(self):
        """GET /api/dashboard/stats should work"""
        res = self.session.get(f"{BASE_URL}/api/dashboard/stats")
        assert res.status_code == 200, f"Dashboard stats failed: {res.text}"
        data = res.json()
        assert "total_packages" in data or "active_journeys" in data, "Invalid stats response"
        print("✓ Dashboard stats endpoint working")
    
    def test_heatmap_endpoint(self):
        """GET /api/analytics/heatmap should work"""
        res = self.session.get(f"{BASE_URL}/api/analytics/heatmap")
        assert res.status_code == 200, f"Heatmap failed: {res.text}"
        print("✓ Heatmap endpoint working")
    
    def test_quality_report_endpoint(self):
        """GET /api/reports/quality should work"""
        res = self.session.get(f"{BASE_URL}/api/reports/quality")
        assert res.status_code == 200, f"Quality report failed: {res.text}"
        print("✓ Quality report endpoint working")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
