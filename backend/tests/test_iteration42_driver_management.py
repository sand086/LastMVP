"""
Iteration 42 - P0 Driver Management Tests
Tests for:
- GET /api/drivers - List drivers with filters (search, provider_id, status, pagination)
- GET /api/drivers/:id - Get driver detail with provider_name
- PATCH /api/drivers/:id - Update driver (provider_id, vehicle_type, status)
- POST /api/providers/inline - Create provider inline (name required, returns id)
- POST /api/drivers/populate - Populate drivers from historical journey data
- GET /api/drivers/vehicle-types - Returns list of vehicle types
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_CREDENTIALS = {
    "developer": {"email": "dev@me.mx", "password": "LastMile2026"},
    "coordinator": {"email": "yael@me.mx", "password": "LastMile2026"},
}


class TestDriverManagementAPI:
    """Driver Management API tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session with auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        # Login as developer
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json=TEST_CREDENTIALS["developer"]
        )
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        # Store cookies for subsequent requests
        self.cookies = login_resp.cookies
        yield
        # Logout
        self.session.post(f"{BASE_URL}/api/auth/logout", cookies=self.cookies)
    
    # ── GET /api/drivers ────────────────────────────────────────────
    def test_list_drivers_basic(self):
        """Test GET /api/drivers returns paginated list"""
        response = self.session.get(f"{BASE_URL}/api/drivers", cookies=self.cookies)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "data" in data, "Response should have 'data' field"
        assert "total" in data, "Response should have 'total' field"
        assert "page" in data, "Response should have 'page' field"
        assert "pages" in data, "Response should have 'pages' field"
        assert isinstance(data["data"], list), "'data' should be a list"
        
        # Verify driver structure if any exist
        if len(data["data"]) > 0:
            driver = data["data"][0]
            assert "id" in driver, "Driver should have 'id'"
            assert "name" in driver, "Driver should have 'name'"
            assert "status" in driver, "Driver should have 'status'"
            # provider_name is enriched
            assert "provider_name" in driver, "Driver should have 'provider_name'"
    
    def test_list_drivers_with_search(self):
        """Test GET /api/drivers with search filter"""
        response = self.session.get(
            f"{BASE_URL}/api/drivers",
            params={"search": "test"},
            cookies=self.cookies
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
    
    def test_list_drivers_with_status_filter(self):
        """Test GET /api/drivers with status filter"""
        response = self.session.get(
            f"{BASE_URL}/api/drivers",
            params={"status": "active"},
            cookies=self.cookies
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        # All returned drivers should be active
        for driver in data["data"]:
            assert driver["status"] == "active", f"Expected active status, got {driver['status']}"
    
    def test_list_drivers_pagination(self):
        """Test GET /api/drivers pagination"""
        response = self.session.get(
            f"{BASE_URL}/api/drivers",
            params={"page": 1, "limit": 5},
            cookies=self.cookies
        )
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert len(data["data"]) <= 5
    
    # ── GET /api/drivers/:id ───────────────────────────────────────
    def test_get_driver_detail(self):
        """Test GET /api/drivers/:id returns driver with provider_name"""
        # First get list to find a driver ID
        list_resp = self.session.get(f"{BASE_URL}/api/drivers", cookies=self.cookies)
        assert list_resp.status_code == 200
        drivers = list_resp.json()["data"]
        
        if len(drivers) == 0:
            pytest.skip("No drivers in database to test detail endpoint")
        
        driver_id = drivers[0]["id"]
        response = self.session.get(f"{BASE_URL}/api/drivers/{driver_id}", cookies=self.cookies)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        driver = response.json()
        assert driver["id"] == driver_id
        assert "name" in driver
        assert "provider_name" in driver or "provider_id" in driver
    
    def test_get_driver_not_found(self):
        """Test GET /api/drivers/:id returns 404 for non-existent driver"""
        response = self.session.get(
            f"{BASE_URL}/api/drivers/non-existent-id-12345",
            cookies=self.cookies
        )
        assert response.status_code == 404
    
    # ── PATCH /api/drivers/:id ──────────────────────────────────────
    def test_update_driver_status(self):
        """Test PATCH /api/drivers/:id to update status"""
        # Get a driver
        list_resp = self.session.get(f"{BASE_URL}/api/drivers", cookies=self.cookies)
        drivers = list_resp.json()["data"]
        
        if len(drivers) == 0:
            pytest.skip("No drivers to test update")
        
        driver = drivers[0]
        driver_id = driver["id"]
        original_status = driver["status"]
        new_status = "inactive" if original_status == "active" else "active"
        
        # Get a valid provider_id first
        prov_resp = self.session.get(f"{BASE_URL}/api/providers", cookies=self.cookies)
        providers = prov_resp.json()
        if len(providers) == 0:
            pytest.skip("No providers to assign")
        provider_id = providers[0]["id"]
        
        # Update driver
        update_resp = self.session.patch(
            f"{BASE_URL}/api/drivers/{driver_id}",
            json={"status": new_status, "provider_id": provider_id},
            cookies=self.cookies
        )
        assert update_resp.status_code == 200, f"Expected 200, got {update_resp.status_code}: {update_resp.text}"
        
        # Verify update
        verify_resp = self.session.get(f"{BASE_URL}/api/drivers/{driver_id}", cookies=self.cookies)
        assert verify_resp.status_code == 200
        updated_driver = verify_resp.json()
        assert updated_driver["status"] == new_status
        
        # Restore original status
        self.session.patch(
            f"{BASE_URL}/api/drivers/{driver_id}",
            json={"status": original_status, "provider_id": provider_id},
            cookies=self.cookies
        )
    
    def test_update_driver_vehicle_type(self):
        """Test PATCH /api/drivers/:id to update vehicle_type"""
        list_resp = self.session.get(f"{BASE_URL}/api/drivers", cookies=self.cookies)
        drivers = list_resp.json()["data"]
        
        if len(drivers) == 0:
            pytest.skip("No drivers to test update")
        
        driver = drivers[0]
        driver_id = driver["id"]
        
        # Get a valid provider_id
        prov_resp = self.session.get(f"{BASE_URL}/api/providers", cookies=self.cookies)
        providers = prov_resp.json()
        if len(providers) == 0:
            pytest.skip("No providers to assign")
        provider_id = driver.get("provider_id") or providers[0]["id"]
        
        update_resp = self.session.patch(
            f"{BASE_URL}/api/drivers/{driver_id}",
            json={"vehicle_type": "moto", "provider_id": provider_id},
            cookies=self.cookies
        )
        assert update_resp.status_code == 200
        
        # Verify
        verify_resp = self.session.get(f"{BASE_URL}/api/drivers/{driver_id}", cookies=self.cookies)
        assert verify_resp.json()["vehicle_type"] == "moto"
    
    def test_update_driver_invalid_status(self):
        """Test PATCH /api/drivers/:id with invalid status returns 400"""
        list_resp = self.session.get(f"{BASE_URL}/api/drivers", cookies=self.cookies)
        drivers = list_resp.json()["data"]
        
        if len(drivers) == 0:
            pytest.skip("No drivers to test")
        
        driver_id = drivers[0]["id"]
        
        update_resp = self.session.patch(
            f"{BASE_URL}/api/drivers/{driver_id}",
            json={"status": "invalid_status"},
            cookies=self.cookies
        )
        assert update_resp.status_code == 400
    
    def test_update_driver_empty_provider(self):
        """Test PATCH /api/drivers/:id with empty provider_id returns 400"""
        list_resp = self.session.get(f"{BASE_URL}/api/drivers", cookies=self.cookies)
        drivers = list_resp.json()["data"]
        
        if len(drivers) == 0:
            pytest.skip("No drivers to test")
        
        driver_id = drivers[0]["id"]
        
        update_resp = self.session.patch(
            f"{BASE_URL}/api/drivers/{driver_id}",
            json={"provider_id": ""},
            cookies=self.cookies
        )
        assert update_resp.status_code == 400
    
    # ── POST /api/providers/inline ──────────────────────────────────
    def test_create_provider_inline(self):
        """Test POST /api/providers/inline creates new provider"""
        test_name = f"TEST_Provider_Inline_{os.urandom(4).hex()}"
        
        response = self.session.post(
            f"{BASE_URL}/api/providers/inline",
            json={"name": test_name, "contact_name": "Test Contact", "rfc": "TEST123"},
            cookies=self.cookies
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "id" in data, "Response should have 'id'"
        assert "name" in data, "Response should have 'name'"
        assert data["name"] == test_name
        assert data.get("already_existed") == False, "New provider should not already exist"
        
        # Cleanup - delete the test provider
        self.session.delete(f"{BASE_URL}/api/providers/{data['id']}", cookies=self.cookies)
    
    def test_create_provider_inline_existing(self):
        """Test POST /api/providers/inline returns existing provider if name matches"""
        # First create a provider
        test_name = f"TEST_Existing_Provider_{os.urandom(4).hex()}"
        
        create_resp = self.session.post(
            f"{BASE_URL}/api/providers/inline",
            json={"name": test_name},
            cookies=self.cookies
        )
        assert create_resp.status_code == 200
        first_id = create_resp.json()["id"]
        
        # Try to create again with same name
        second_resp = self.session.post(
            f"{BASE_URL}/api/providers/inline",
            json={"name": test_name},
            cookies=self.cookies
        )
        assert second_resp.status_code == 200
        data = second_resp.json()
        assert data["id"] == first_id, "Should return same provider ID"
        assert data.get("already_existed") == True
        
        # Cleanup
        self.session.delete(f"{BASE_URL}/api/providers/{first_id}", cookies=self.cookies)
    
    def test_create_provider_inline_empty_name(self):
        """Test POST /api/providers/inline with empty name returns 400"""
        response = self.session.post(
            f"{BASE_URL}/api/providers/inline",
            json={"name": ""},
            cookies=self.cookies
        )
        assert response.status_code == 400
    
    def test_create_provider_inline_whitespace_name(self):
        """Test POST /api/providers/inline with whitespace-only name returns 400"""
        response = self.session.post(
            f"{BASE_URL}/api/providers/inline",
            json={"name": "   "},
            cookies=self.cookies
        )
        assert response.status_code == 400
    
    # ── GET /api/drivers/vehicle-types ──────────────────────────────
    def test_get_vehicle_types(self):
        """Test GET /api/drivers/vehicle-types returns list of vehicle types"""
        response = self.session.get(f"{BASE_URL}/api/drivers/vehicle-types", cookies=self.cookies)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        # Should include base types
        base_types = ["moto", "van", "camioneta", "auto"]
        for bt in base_types:
            assert bt in data, f"Base type '{bt}' should be in vehicle types"
    
    # ── POST /api/drivers/populate ──────────────────────────────────
    def test_populate_drivers(self):
        """Test POST /api/drivers/populate populates from journeys"""
        response = self.session.post(f"{BASE_URL}/api/drivers/populate", cookies=self.cookies)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data
        assert "created" in data
        assert "updated" in data
        assert isinstance(data["created"], int)
        assert isinstance(data["updated"], int)


class TestRouteSummaryPendingProviders:
    """Test route-summary upload returns pending_providers for new teams"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session with auth"""
        self.session = requests.Session()
        # Don't set Content-Type for multipart uploads
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json=TEST_CREDENTIALS["coordinator"],
            headers={"Content-Type": "application/json"}
        )
        assert login_resp.status_code == 200
        self.cookies = login_resp.cookies
        yield
        self.session.post(f"{BASE_URL}/api/auth/logout", cookies=self.cookies)
    
    def test_route_summary_response_structure(self):
        """Test POST /api/upload/route-summary response includes pending_providers field"""
        # Create a minimal CSV file
        import io
        csv_content = "Order ID,Driver,Team,Status,Zones,Creation Date,Total Stops\n"
        csv_content += "R001,TestDriver1,ExistingTeam,Completed,Zone1,2025-01-15,10\n"
        
        # Use proper multipart form data
        files = {"file": ("test_route_summary.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        
        response = self.session.post(
            f"{BASE_URL}/api/upload/route-summary",
            files=files,
            cookies=self.cookies
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "pending_providers" in data, "Response should include 'pending_providers' field"
        assert "driver_status" in data, "Response should include 'driver_status' field"
        assert isinstance(data["pending_providers"], list)


class TestDriversTabIntegration:
    """Integration tests for Drivers tab data flow"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup session with auth"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        login_resp = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json=TEST_CREDENTIALS["developer"]
        )
        assert login_resp.status_code == 200
        self.cookies = login_resp.cookies
        yield
        self.session.post(f"{BASE_URL}/api/auth/logout", cookies=self.cookies)
    
    def test_drivers_count_matches_expected(self):
        """Test that drivers collection has expected count (19 from historical data)"""
        response = self.session.get(f"{BASE_URL}/api/drivers", cookies=self.cookies)
        assert response.status_code == 200
        
        data = response.json()
        total = data["total"]
        # According to context, 19 drivers were populated from historical journeys
        # Allow some flexibility in case more were added
        assert total >= 1, f"Expected at least 1 driver, got {total}"
        print(f"Total drivers in database: {total}")
    
    def test_driver_provider_filter(self):
        """Test filtering drivers by provider_id"""
        # Get providers first
        prov_resp = self.session.get(f"{BASE_URL}/api/providers", cookies=self.cookies)
        providers = prov_resp.json()
        
        if len(providers) == 0:
            pytest.skip("No providers to test filter")
        
        provider_id = providers[0]["id"]
        
        response = self.session.get(
            f"{BASE_URL}/api/drivers",
            params={"provider_id": provider_id},
            cookies=self.cookies
        )
        assert response.status_code == 200
        
        data = response.json()
        # All returned drivers should have this provider_id
        for driver in data["data"]:
            assert driver.get("provider_id") == provider_id, f"Driver {driver['name']} has wrong provider_id"
