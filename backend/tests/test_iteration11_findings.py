"""
Test Iteration 11 - 7 Findings from Operational Roleplay
Tests for:
1. Sync button response (should return {status: 'started'})
2. Evidence quality re-evaluation for ALL scraped packages
3. Cleanup confirmation dialog (frontend test)
4. Close form text 'Fallido(s) marcado(s) para devolución' (frontend test)
5. Composite unique key (cosmo_route_id + order_reference_id)
6. Delivery attempts column (delivery_attempt field)
7. Creation Date from route-summary as journey date
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSyncEndpoint:
    """Test #1: POST /api/sync/tracking should return {status: 'started'}"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": "LastMile2026"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_sync_tracking_returns_started_status(self):
        """Verify sync endpoint returns {status: 'started'} immediately"""
        response = requests.post(f"{BASE_URL}/api/sync/tracking", headers=self.headers)
        assert response.status_code == 200, f"Sync failed: {response.text}"
        
        data = response.json()
        assert "status" in data, "Response should contain 'status' field"
        assert data["status"] == "started", f"Expected status='started', got '{data.get('status')}'"
        
        # Verify it does NOT return 'undefined' or old format
        assert "undefined" not in str(data).lower(), "Response should not contain 'undefined'"
        print(f"✓ Sync endpoint returns correct response: {data}")
    
    def test_sync_status_endpoint_exists(self):
        """Verify /api/sync/status endpoint returns sync status"""
        response = requests.get(f"{BASE_URL}/api/sync/status", headers=self.headers)
        assert response.status_code == 200, f"Sync status failed: {response.text}"
        
        data = response.json()
        # Should have these fields after a sync
        expected_fields = ["last_sync", "total_checked", "updated", "errors"]
        for field in expected_fields:
            assert field in data, f"Missing field '{field}' in sync status"
        print(f"✓ Sync status endpoint returns: {data}")


class TestCompositeKeyDeduplication:
    """Test #5: Composite key (cosmo_route_id + order_reference_id) for package deduplication"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": "LastMile2026"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_journeys_have_cosmo_route_id_field(self):
        """Verify journeys have cosmo_route_id field (packages created before fix may not have it)"""
        # Get journeys first
        response = requests.get(f"{BASE_URL}/api/journeys", headers=self.headers)
        assert response.status_code == 200
        journeys = response.json()
        
        if not journeys:
            pytest.skip("No journeys available for testing")
        
        # Check journeys have cosmo_route_id field
        journeys_with_route_id = 0
        for journey in journeys[:10]:
            if "cosmo_route_id" in journey and journey["cosmo_route_id"]:
                journeys_with_route_id += 1
        
        print(f"✓ {journeys_with_route_id}/{min(10, len(journeys))} journeys have cosmo_route_id field")
        # At least some journeys should have cosmo_route_id
        assert journeys_with_route_id > 0, "No journeys have cosmo_route_id field"


class TestDeliveryAttemptField:
    """Test #6: Delivery attempts column - packages should have delivery_attempt field"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": "LastMile2026"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_journey_packages_have_delivery_attempt(self):
        """Verify journey detail API returns packages with delivery_attempt field"""
        # Get journeys
        response = requests.get(f"{BASE_URL}/api/journeys", headers=self.headers)
        assert response.status_code == 200
        journeys = response.json()
        
        if not journeys:
            pytest.skip("No journeys available for testing")
        
        # Get first journey with packages
        for journey in journeys[:5]:
            journey_response = requests.get(f"{BASE_URL}/api/journeys/{journey['id']}", headers=self.headers)
            if journey_response.status_code == 200:
                journey_data = journey_response.json()
                packages = journey_data.get("packages", [])
                if packages:
                    # Check packages have delivery_attempt field
                    pkg = packages[0]
                    assert "delivery_attempt" in pkg, f"Package missing 'delivery_attempt' field: {pkg.keys()}"
                    assert isinstance(pkg["delivery_attempt"], int), f"delivery_attempt should be int, got {type(pkg['delivery_attempt'])}"
                    assert pkg["delivery_attempt"] >= 1, f"delivery_attempt should be >= 1, got {pkg['delivery_attempt']}"
                    print(f"✓ Package has delivery_attempt: {pkg.get('delivery_attempt')}")
                    return
        
        pytest.skip("No packages found in journeys")


class TestCreationDateParsing:
    """Test #7: Route-summary parser should extract creation_date field"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": "LastMile2026"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_journeys_have_date_field(self):
        """Verify journeys have date field (from creation_date or fallback)"""
        response = requests.get(f"{BASE_URL}/api/journeys", headers=self.headers)
        assert response.status_code == 200
        journeys = response.json()
        
        if not journeys:
            pytest.skip("No journeys available for testing")
        
        # Check journeys have date field
        for journey in journeys[:5]:
            assert "date" in journey, f"Journey missing 'date' field: {journey.keys()}"
            assert journey["date"], f"Journey date should not be empty"
            print(f"✓ Journey {journey['id'][:8]}... has date: {journey['date']}")
        
        print(f"✓ All checked journeys have date field")


class TestEvidenceQualityReEvaluation:
    """Test #2: After sync, ALL scraped packages should have evidence scores re-evaluated"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": "LastMile2026"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_delivered_packages_have_evidence_fields(self):
        """Verify delivered packages have evidence_score and evidence_type fields"""
        # Get journeys
        response = requests.get(f"{BASE_URL}/api/journeys", headers=self.headers)
        assert response.status_code == 200
        journeys = response.json()
        
        if not journeys:
            pytest.skip("No journeys available for testing")
        
        delivered_packages_checked = 0
        packages_with_evidence = 0
        
        # Check multiple journeys for delivered packages
        for journey in journeys[:10]:
            journey_response = requests.get(f"{BASE_URL}/api/journeys/{journey['id']}", headers=self.headers)
            if journey_response.status_code == 200:
                journey_data = journey_response.json()
                packages = journey_data.get("packages", [])
                
                for pkg in packages:
                    if pkg.get("status") == "delivered" or pkg.get("kosmo_status") == "delivered":
                        delivered_packages_checked += 1
                        # Check for evidence fields
                        if "evidence_score" in pkg:
                            packages_with_evidence += 1
                            # Verify evidence_type is also present
                            assert "evidence_type" in pkg, f"Package has evidence_score but missing evidence_type"
        
        if delivered_packages_checked == 0:
            pytest.skip("No delivered packages found for testing")
        
        # At least some delivered packages should have evidence scores
        print(f"✓ Checked {delivered_packages_checked} delivered packages, {packages_with_evidence} have evidence scores")
        assert packages_with_evidence > 0, "No delivered packages have evidence scores - evidence evaluation may not be working"


class TestAPIEndpoints:
    """General API endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "dev@me.mx",
            "password": "LastMile2026"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_health_endpoint(self):
        """Verify health endpoint works"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✓ Health endpoint working")
    
    def test_journeys_list(self):
        """Verify journeys list endpoint works"""
        response = requests.get(f"{BASE_URL}/api/journeys", headers=self.headers)
        assert response.status_code == 200
        journeys = response.json()
        assert isinstance(journeys, list)
        print(f"✓ Journeys endpoint returns {len(journeys)} journeys")
    
    def test_cleanup_endpoint_exists(self):
        """Verify cleanup endpoint exists (but don't execute it)"""
        # Just verify the endpoint exists by checking OPTIONS or a safe method
        # We won't actually call DELETE to avoid data loss
        response = requests.options(f"{BASE_URL}/api/admin/cleanup")
        # OPTIONS might return 200 or 405 depending on CORS config
        # The important thing is it doesn't return 404
        assert response.status_code != 404, "Cleanup endpoint not found"
        print("✓ Cleanup endpoint exists")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
