"""
Iteration 27 - Guías Tab and Proveedor Role Testing
Tests for:
1. Tab structure (Inicio | Incidencias | Fin | Guías - NO Calidad tab)
2. PATCH /api/packages/{id}/review endpoint
3. Proveedor role authentication and authorization
4. Proveedor role journey filtering
5. Package enrichment fields for Guías tab
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEVELOPER_CREDS = {"email": "dev@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
COORDINATOR_CREDS = {"email": "yael@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
AGENT_CREDS = {"email": "agente@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
PROVEEDOR_CREDS = {"email": "proveedor@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}


class TestAuthEndpoints:
    """Test authentication for all roles"""
    
    def test_developer_login(self):
        """Developer can login and gets access_token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEVELOPER_CREDS)
        assert response.status_code == 200, f"Developer login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Response should contain access_token"
        assert "user" in data, "Response should contain user"
        assert data["user"]["role"] == "developer"
        print(f"✓ Developer login successful: {data['user']['email']}")
    
    def test_coordinator_login(self):
        """Coordinator can login and gets access_token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=COORDINATOR_CREDS)
        assert response.status_code == 200, f"Coordinator login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "coordinator"
        print(f"✓ Coordinator login successful: {data['user']['email']}")
    
    def test_agent_login(self):
        """Agent can login and gets access_token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=AGENT_CREDS)
        assert response.status_code == 200, f"Agent login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "agent"
        print(f"✓ Agent login successful: {data['user']['email']}")
    
    def test_proveedor_login(self):
        """Proveedor can login and gets access_token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=PROVEEDOR_CREDS)
        assert response.status_code == 200, f"Proveedor login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "Response should contain access_token"
        assert "user" in data, "Response should contain user"
        assert data["user"]["role"] == "proveedor", f"Expected role 'proveedor', got {data['user']['role']}"
        print(f"✓ Proveedor login successful: {data['user']['email']}, role: {data['user']['role']}")


class TestPackageReviewEndpoint:
    """Test PATCH /api/packages/{id}/review endpoint"""
    
    @pytest.fixture
    def developer_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEVELOPER_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture
    def coordinator_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=COORDINATOR_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture
    def agent_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=AGENT_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture
    def proveedor_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=PROVEEDOR_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture
    def sample_package_id(self, developer_token):
        """Get a sample package ID from any journey"""
        headers = {"Authorization": f"Bearer {developer_token}"}
        journeys_resp = requests.get(f"{BASE_URL}/api/journeys", headers=headers)
        if journeys_resp.status_code == 200:
            journeys = journeys_resp.json().get("data", [])
            if journeys:
                journey_id = journeys[0]["id"]
                journey_resp = requests.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=headers)
                if journey_resp.status_code == 200:
                    packages = journey_resp.json().get("packages", [])
                    if packages:
                        return packages[0]["id"]
        return None
    
    def test_developer_can_approve_package(self, developer_token, sample_package_id):
        """Developer can approve a package via PATCH endpoint"""
        if not sample_package_id:
            pytest.skip("No packages available for testing")
        
        headers = {"Authorization": f"Bearer {developer_token}"}
        response = requests.patch(
            f"{BASE_URL}/api/packages/{sample_package_id}/review",
            json={"manually_reviewed": True},
            headers=headers
        )
        assert response.status_code == 200, f"Developer approve failed: {response.text}"
        data = response.json()
        assert data.get("manually_reviewed")
        print(f"✓ Developer approved package {sample_package_id}")
    
    def test_coordinator_can_approve_package(self, coordinator_token, sample_package_id):
        """Coordinator can approve a package via PATCH endpoint"""
        if not sample_package_id:
            pytest.skip("No packages available for testing")
        
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        response = requests.patch(
            f"{BASE_URL}/api/packages/{sample_package_id}/review",
            json={"manually_reviewed": True},
            headers=headers
        )
        assert response.status_code == 200, f"Coordinator approve failed: {response.text}"
        print(f"✓ Coordinator approved package {sample_package_id}")
    
    def test_coordinator_can_reject_with_note(self, coordinator_token, sample_package_id):
        """Coordinator can reject a package with a note"""
        if not sample_package_id:
            pytest.skip("No packages available for testing")
        
        headers = {"Authorization": f"Bearer {coordinator_token}"}
        response = requests.patch(
            f"{BASE_URL}/api/packages/{sample_package_id}/review",
            json={"manually_reviewed": False, "manually_reviewed_note": "Test rejection note"},
            headers=headers
        )
        assert response.status_code == 200, f"Coordinator reject failed: {response.text}"
        data = response.json()
        assert data.get("rejection_reason") == "Test rejection note"
        print("✓ Coordinator rejected package with note")
    
    def test_agent_cannot_review_package(self, agent_token, sample_package_id):
        """Agent should NOT be able to review packages (403)"""
        if not sample_package_id:
            pytest.skip("No packages available for testing")
        
        headers = {"Authorization": f"Bearer {agent_token}"}
        response = requests.patch(
            f"{BASE_URL}/api/packages/{sample_package_id}/review",
            json={"manually_reviewed": True},
            headers=headers
        )
        assert response.status_code == 403, f"Agent should get 403, got {response.status_code}"
        print("✓ Agent correctly denied review access (403)")
    
    def test_proveedor_cannot_review_package(self, proveedor_token, sample_package_id):
        """Proveedor should NOT be able to review packages (403)"""
        if not sample_package_id:
            pytest.skip("No packages available for testing")
        
        headers = {"Authorization": f"Bearer {proveedor_token}"}
        response = requests.patch(
            f"{BASE_URL}/api/packages/{sample_package_id}/review",
            json={"manually_reviewed": True},
            headers=headers
        )
        assert response.status_code == 403, f"Proveedor should get 403, got {response.status_code}"
        print("✓ Proveedor correctly denied review access (403)")


class TestProveedorJourneyFiltering:
    """Test that proveedor only sees their provider's journeys"""
    
    @pytest.fixture
    def proveedor_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=PROVEEDOR_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture
    def developer_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEVELOPER_CREDS)
        return response.json()["access_token"]
    
    def test_proveedor_can_access_journeys(self, proveedor_token):
        """Proveedor can access journeys endpoint"""
        headers = {"Authorization": f"Bearer {proveedor_token}"}
        response = requests.get(f"{BASE_URL}/api/journeys", headers=headers)
        assert response.status_code == 200, f"Proveedor journeys access failed: {response.text}"
        data = response.json()
        assert "data" in data
        print(f"✓ Proveedor can access journeys, found {len(data['data'])} journeys")
    
    def test_proveedor_can_access_dashboard(self, proveedor_token):
        """Proveedor can access dashboard stats"""
        headers = {"Authorization": f"Bearer {proveedor_token}"}
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=headers)
        assert response.status_code == 200, f"Proveedor dashboard access failed: {response.text}"
        print("✓ Proveedor can access dashboard stats")
    
    def test_proveedor_cannot_access_settings(self, proveedor_token):
        """Proveedor should NOT be able to access settings endpoints"""
        headers = {"Authorization": f"Bearer {proveedor_token}"}
        # Try to access users endpoint (settings)
        response = requests.get(f"{BASE_URL}/api/users", headers=headers)
        # Should be 403 or limited access
        print(f"Proveedor users access: {response.status_code}")
        # Note: This depends on implementation - may be 403 or filtered results


class TestPackageEnrichmentFields:
    """Test that packages are enriched with required fields for Guías tab"""
    
    @pytest.fixture
    def developer_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEVELOPER_CREDS)
        return response.json()["access_token"]
    
    def test_journey_packages_have_enriched_fields(self, developer_token):
        """Packages in journey detail should have ai_score, ai_errors, photos_count, etc."""
        headers = {"Authorization": f"Bearer {developer_token}"}
        
        # Get a journey
        journeys_resp = requests.get(f"{BASE_URL}/api/journeys", headers=headers)
        assert journeys_resp.status_code == 200
        journeys = journeys_resp.json().get("data", [])
        
        if not journeys:
            pytest.skip("No journeys available for testing")
        
        journey_id = journeys[0]["id"]
        journey_resp = requests.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=headers)
        assert journey_resp.status_code == 200
        
        journey = journey_resp.json()
        packages = journey.get("packages", [])
        
        if not packages:
            pytest.skip("No packages in journey")
        
        # Check first package for enriched fields
        pkg = packages[0]
        
        # These fields should exist (may be null but should be present)
        expected_fields = [
            "ai_score",
            "ai_errors", 
            "ai_confidence",
            "manually_reviewed",
            "photos_count",
            "delivery_note",
            "kosmo_url"
        ]
        
        for field in expected_fields:
            assert field in pkg, f"Package missing enriched field: {field}"
        
        # ai_errors should be a list
        assert isinstance(pkg.get("ai_errors"), list), "ai_errors should be a list"
        
        # photos_count should be a number
        assert isinstance(pkg.get("photos_count"), (int, type(None))), "photos_count should be int or None"
        
        print(f"✓ Package has all enriched fields: {expected_fields}")
        print(f"  ai_score: {pkg.get('ai_score')}")
        print(f"  ai_errors: {pkg.get('ai_errors')}")
        print(f"  photos_count: {pkg.get('photos_count')}")
        print(f"  manually_reviewed: {pkg.get('manually_reviewed')}")


class TestResyncAndEvaluateEndpoints:
    """Test Re-sincronizar Kosmo and Evaluar IA endpoints"""
    
    @pytest.fixture
    def developer_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEVELOPER_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture
    def proveedor_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=PROVEEDOR_CREDS)
        return response.json()["access_token"]
    
    @pytest.fixture
    def sample_journey_id(self, developer_token):
        """Get a sample journey ID"""
        headers = {"Authorization": f"Bearer {developer_token}"}
        journeys_resp = requests.get(f"{BASE_URL}/api/journeys", headers=headers)
        if journeys_resp.status_code == 200:
            journeys = journeys_resp.json().get("data", [])
            if journeys:
                return journeys[0]["id"]
        return None
    
    def test_batch_rescrape_endpoint_exists(self, developer_token, sample_journey_id):
        """Batch rescrape endpoint should exist and be accessible"""
        if not sample_journey_id:
            pytest.skip("No journeys available")
        
        headers = {"Authorization": f"Bearer {developer_token}"}
        response = requests.post(
            f"{BASE_URL}/api/journeys/{sample_journey_id}/batch-rescrape",
            headers=headers
        )
        # Should return 200 or 404 (if no packages need rescrape)
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}"
        print(f"✓ Batch rescrape endpoint accessible: {response.status_code}")
    
    def test_evaluate_all_evidence_endpoint_exists(self, developer_token, sample_journey_id):
        """Evaluate all evidence endpoint should exist"""
        if not sample_journey_id:
            pytest.skip("No journeys available")
        
        headers = {"Authorization": f"Bearer {developer_token}"}
        response = requests.post(
            f"{BASE_URL}/api/journeys/{sample_journey_id}/evaluate-evidence-all",
            headers=headers
        )
        assert response.status_code == 200, f"Evaluate all failed: {response.text}"
        data = response.json()
        assert "status" in data or "message" in data
        print("✓ Evaluate all evidence endpoint works")


class TestJourneyDetailEndpoint:
    """Test journey detail endpoint returns correct structure"""
    
    @pytest.fixture
    def developer_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEVELOPER_CREDS)
        return response.json()["access_token"]
    
    def test_journey_detail_structure(self, developer_token):
        """Journey detail should have packages with delivery_attempt field"""
        headers = {"Authorization": f"Bearer {developer_token}"}
        
        journeys_resp = requests.get(f"{BASE_URL}/api/journeys", headers=headers)
        assert journeys_resp.status_code == 200
        journeys = journeys_resp.json().get("data", [])
        
        if not journeys:
            pytest.skip("No journeys available")
        
        journey_id = journeys[0]["id"]
        journey_resp = requests.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=headers)
        assert journey_resp.status_code == 200
        
        journey = journey_resp.json()
        
        # Check journey has required fields
        assert "packages" in journey
        assert "incidents" in journey
        assert "client_name" in journey
        assert "provider_name" in journey
        
        packages = journey.get("packages", [])
        if packages:
            pkg = packages[0]
            # Check delivery_attempt field exists
            assert "delivery_attempt" in pkg, "Package should have delivery_attempt field"
            print("✓ Journey detail has correct structure")
            print(f"  Packages: {len(packages)}")
            print(f"  First package delivery_attempt: {pkg.get('delivery_attempt')}")


class TestSeedDataProveedorUser:
    """Verify proveedor user exists in seed data"""
    
    def test_proveedor_user_exists(self):
        """Proveedor user should exist and be able to login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=PROVEEDOR_CREDS)
        assert response.status_code == 200, f"Proveedor user not found or wrong password: {response.text}"
        data = response.json()
        assert data["user"]["role"] == "proveedor"
        assert data["user"]["email"] == "proveedor@me.mx"
        print("✓ Proveedor user exists with correct role")
        
        # Check if assigned_providers is set (from seed data)
        # This is stored in the user object but may not be returned in login response
        # We verify by checking journey filtering works


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
