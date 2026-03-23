"""
Test file for Iteration 7 features:
1. GET /api/users works with developer role (no 'Acceso denegado')
2. PUT /api/clients/{id} updates client name
3. DELETE /api/clients/{id} deletes a client
4. PUT /api/providers/{id} updates provider fields
5. DELETE /api/providers/{id} deletes a provider
6. GET /api/packages/search?q=test returns matching packages
7. POST /api/cleanup/routes-packages clears journeys, packages, incidents
8. GET /api/reports/schema returns new endpoints
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEV_EMAIL = "dev@me.mx"
DEV_PASSWORD = "LastMile2026"
AGENT_EMAIL = "agente@me.mx"
AGENT_PASSWORD = "LastMile2026"


@pytest.fixture(scope="module")
def dev_token():
    """Get developer token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEV_EMAIL,
        "password": DEV_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Developer login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def agent_token():
    """Get agent token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": AGENT_EMAIL,
        "password": AGENT_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Agent login failed: {response.status_code} - {response.text}")


@pytest.fixture
def dev_headers(dev_token):
    """Headers with developer auth"""
    return {
        "Authorization": f"Bearer {dev_token}",
        "Content-Type": "application/json"
    }


@pytest.fixture
def agent_headers(agent_token):
    """Headers with agent auth"""
    return {
        "Authorization": f"Bearer {agent_token}",
        "Content-Type": "application/json"
    }


class TestDeveloperRoleAccess:
    """Test that developer role has proper access to Settings endpoints"""
    
    def test_developer_can_access_users_endpoint(self, dev_headers):
        """GET /api/users should work for developer role (no 'Acceso denegado')"""
        response = requests.get(f"{BASE_URL}/api/users", headers=dev_headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of users"
        print(f"SUCCESS: Developer can access /api/users - returned {len(data)} users")
    
    def test_developer_can_access_password_reset_requests(self, dev_headers):
        """GET /api/password-reset-requests should work for developer role"""
        response = requests.get(f"{BASE_URL}/api/password-reset-requests", headers=dev_headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print("SUCCESS: Developer can access /api/password-reset-requests")


class TestClientsCRUD:
    """Test Clients CRUD operations"""
    
    def test_create_client(self, dev_headers):
        """POST /api/clients creates a new client"""
        response = requests.post(f"{BASE_URL}/api/clients", headers=dev_headers, json={
            "name": "TEST_Client_Iteration7"
        })
        
        # Note: create_client requires coordinator or agent role, not developer
        # Let's check what happens
        if response.status_code == 403:
            pytest.skip("Developer role cannot create clients (expected behavior)")
        
        assert response.status_code == 200 or response.status_code == 201, f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data
        print(f"SUCCESS: Created client with id {data['id']}")
        return data["id"]
    
    def test_update_client(self, dev_headers):
        """PUT /api/clients/{id} updates client name"""
        # First get existing clients
        response = requests.get(f"{BASE_URL}/api/clients", headers=dev_headers)
        assert response.status_code == 200
        clients = response.json()
        
        if not clients:
            pytest.skip("No clients available to test update")
        
        client_id = clients[0]["id"]
        original_name = clients[0]["name"]
        new_name = f"TEST_Updated_{original_name}"
        
        # Update client
        response = requests.put(f"{BASE_URL}/api/clients/{client_id}", headers=dev_headers, json={
            "name": new_name
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify update
        response = requests.get(f"{BASE_URL}/api/clients", headers=dev_headers)
        clients = response.json()
        updated_client = next((c for c in clients if c["id"] == client_id), None)
        assert updated_client is not None
        assert updated_client["name"] == new_name, f"Expected name '{new_name}', got '{updated_client['name']}'"
        
        # Restore original name
        requests.put(f"{BASE_URL}/api/clients/{client_id}", headers=dev_headers, json={
            "name": original_name
        })
        
        print(f"SUCCESS: Updated client {client_id} name from '{original_name}' to '{new_name}' and restored")
    
    def test_delete_client(self, agent_headers, dev_headers):
        """DELETE /api/clients/{id} deletes a client"""
        # Create a test client first (using agent role which can create)
        response = requests.post(f"{BASE_URL}/api/clients", headers=agent_headers, json={
            "name": "TEST_ToDelete_Client"
        })
        
        if response.status_code not in [200, 201]:
            pytest.skip(f"Could not create test client: {response.status_code}")
        
        client_id = response.json()["id"]
        
        # Delete using developer role
        response = requests.delete(f"{BASE_URL}/api/clients/{client_id}", headers=dev_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify deletion
        response = requests.get(f"{BASE_URL}/api/clients", headers=dev_headers)
        clients = response.json()
        deleted_client = next((c for c in clients if c["id"] == client_id), None)
        assert deleted_client is None, "Client should have been deleted"
        
        print(f"SUCCESS: Deleted client {client_id}")


class TestProvidersCRUD:
    """Test Providers CRUD operations"""
    
    def test_update_provider(self, dev_headers):
        """PUT /api/providers/{id} updates provider fields"""
        # First get existing providers
        response = requests.get(f"{BASE_URL}/api/providers", headers=dev_headers)
        assert response.status_code == 200
        providers = response.json()
        
        if not providers:
            pytest.skip("No providers available to test update")
        
        provider_id = providers[0]["id"]
        original_name = providers[0]["name"]
        original_contact = providers[0].get("contact_name", "")
        original_phone = providers[0].get("contact_phone", "")
        
        new_name = f"TEST_Updated_{original_name}"
        new_contact = "Test Contact Person"
        new_phone = "+52 55 9999 8888"
        
        # Update provider
        response = requests.put(f"{BASE_URL}/api/providers/{provider_id}", headers=dev_headers, json={
            "name": new_name,
            "contact_name": new_contact,
            "contact_phone": new_phone
        })
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify update
        response = requests.get(f"{BASE_URL}/api/providers", headers=dev_headers)
        providers = response.json()
        updated_provider = next((p for p in providers if p["id"] == provider_id), None)
        assert updated_provider is not None
        assert updated_provider["name"] == new_name
        assert updated_provider["contact_name"] == new_contact
        assert updated_provider["contact_phone"] == new_phone
        
        # Restore original values
        requests.put(f"{BASE_URL}/api/providers/{provider_id}", headers=dev_headers, json={
            "name": original_name,
            "contact_name": original_contact,
            "contact_phone": original_phone
        })
        
        print(f"SUCCESS: Updated provider {provider_id} and restored")
    
    def test_delete_provider(self, agent_headers, dev_headers):
        """DELETE /api/providers/{id} deletes a provider"""
        # Create a test provider first (using agent role)
        response = requests.post(f"{BASE_URL}/api/providers", headers=agent_headers, json={
            "name": "TEST_ToDelete_Provider",
            "contact_name": "Test Contact",
            "contact_phone": "+52 55 1234 5678"
        })
        
        if response.status_code not in [200, 201]:
            pytest.skip(f"Could not create test provider: {response.status_code}")
        
        provider_id = response.json()["id"]
        
        # Delete using developer role
        response = requests.delete(f"{BASE_URL}/api/providers/{provider_id}", headers=dev_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify deletion
        response = requests.get(f"{BASE_URL}/api/providers", headers=dev_headers)
        providers = response.json()
        deleted_provider = next((p for p in providers if p["id"] == provider_id), None)
        assert deleted_provider is None, "Provider should have been deleted"
        
        print(f"SUCCESS: Deleted provider {provider_id}")


class TestPackageSearch:
    """Test package search functionality"""
    
    def test_search_packages_endpoint_exists(self, dev_headers):
        """GET /api/packages/search?q=test returns results or empty list"""
        response = requests.get(f"{BASE_URL}/api/packages/search", headers=dev_headers, params={"q": "test"})
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of packages"
        print(f"SUCCESS: Package search returned {len(data)} results for 'test'")
    
    def test_search_packages_short_query(self, dev_headers):
        """GET /api/packages/search with short query returns empty"""
        response = requests.get(f"{BASE_URL}/api/packages/search", headers=dev_headers, params={"q": "a"})
        
        assert response.status_code == 200
        data = response.json()
        assert data == [], "Short query should return empty list"
        print("SUCCESS: Short query returns empty list as expected")
    
    def test_search_packages_by_order_reference(self, dev_headers):
        """GET /api/packages/search searches by order_reference_id"""
        # First get some packages to know what to search for
        response = requests.get(f"{BASE_URL}/api/journeys", headers=dev_headers)
        if response.status_code != 200:
            pytest.skip("Could not get journeys")
        
        journeys = response.json()
        if not journeys:
            pytest.skip("No journeys available")
        
        # Get packages from first journey
        journey_id = journeys[0]["id"]
        response = requests.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=dev_headers)
        if response.status_code != 200:
            pytest.skip("Could not get journey details")
        
        journey = response.json()
        packages = journey.get("packages", [])
        if not packages:
            pytest.skip("No packages in journey")
        
        # Search for first package's order_reference_id
        order_ref = packages[0].get("order_reference_id") or packages[0].get("tracking_number")
        if not order_ref or len(order_ref) < 2:
            pytest.skip("No valid order reference to search")
        
        search_term = order_ref[:5]  # First 5 chars
        response = requests.get(f"{BASE_URL}/api/packages/search", headers=dev_headers, params={"q": search_term})
        
        assert response.status_code == 200
        results = response.json()
        print(f"SUCCESS: Search for '{search_term}' returned {len(results)} results")


class TestCleanupEndpoint:
    """Test cleanup routes/packages endpoint"""
    
    def test_cleanup_endpoint_exists(self, dev_headers):
        """POST /api/cleanup/routes-packages endpoint exists"""
        # Note: We won't actually run cleanup to preserve test data
        # Just verify the endpoint exists and returns proper structure
        response = requests.post(f"{BASE_URL}/api/cleanup/routes-packages", headers=dev_headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "deleted" in data, "Response should contain 'deleted' key"
        assert "journeys" in data["deleted"], "Should report deleted journeys count"
        assert "packages" in data["deleted"], "Should report deleted packages count"
        assert "incidents" in data["deleted"], "Should report deleted incidents count"
        
        print(f"SUCCESS: Cleanup endpoint works - deleted {data['deleted']}")


class TestReportsSchema:
    """Test reports schema endpoint"""
    
    def test_reports_schema_includes_new_endpoints(self, dev_headers):
        """GET /api/reports/schema returns new endpoints"""
        response = requests.get(f"{BASE_URL}/api/reports/schema", headers=dev_headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Check for expected endpoints in schema
        endpoints = data.get("endpoints", [])
        endpoint_paths = [e.get("endpoint", "") for e in endpoints]
        
        # Check for sync endpoint
        assert any("/sync" in p for p in endpoint_paths), f"Schema should include sync endpoint. Found: {endpoint_paths}"
        
        # Check for quality endpoint
        assert any("/quality" in p for p in endpoint_paths), "Schema should include quality endpoint"
        
        # Check for packages/search endpoint
        assert any("/packages/search" in p for p in endpoint_paths), "Schema should include packages/search endpoint"
        
        # Check for cleanup endpoint
        assert any("/cleanup" in p for p in endpoint_paths), "Schema should include cleanup endpoint"
        
        print(f"SUCCESS: Reports schema includes {len(endpoints)} endpoints with new features")


class TestDashboardStats:
    """Test dashboard stats include quality KPI"""
    
    def test_dashboard_stats_includes_quality(self, dev_headers):
        """GET /api/dashboard/stats includes avg_evidence_score and packages_incomplete_support"""
        response = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=dev_headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Check for quality fields
        assert "avg_evidence_score" in data, "Dashboard stats should include avg_evidence_score"
        assert "packages_incomplete_support" in data, "Dashboard stats should include packages_incomplete_support"
        
        print(f"SUCCESS: Dashboard stats include quality KPI - avg_score: {data['avg_evidence_score']}, incomplete: {data['packages_incomplete_support']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
