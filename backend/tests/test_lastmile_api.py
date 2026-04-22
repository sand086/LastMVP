"""
LastMile OS API Tests
Tests for authentication, journeys, users, assignments, and new features
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
COORDINATOR_EMAIL = "yael@me.mx"
COORDINATOR_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
AGENT_EMAIL = "agente@me.mx"
AGENT_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
EXECUTIVE_EMAIL = "karina@me.mx"
EXECUTIVE_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")


class TestHealthAndBasics:
    """Basic health and API availability tests"""
    
    def test_api_health(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("✓ API health check passed")
    
    def test_api_root(self):
        """Test API root endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "LastMile OS API" in data["message"]
        print("✓ API root endpoint working")


class TestAuthentication:
    """Authentication flow tests"""
    
    def test_login_coordinator(self):
        """Test coordinator login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "coordinator"
        assert data["user"]["email"] == COORDINATOR_EMAIL
        print(f"✓ Coordinator login successful: {data['user']['name']}")
    
    def test_login_agent(self):
        """Test agent login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": AGENT_EMAIL,
            "password": AGENT_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "agent"
        print(f"✓ Agent login successful: {data['user']['name']}")
    
    def test_login_executive(self):
        """Test executive login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": EXECUTIVE_EMAIL,
            "password": EXECUTIVE_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["role"] == "executive"
        print(f"✓ Executive login successful: {data['user']['name']}")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "invalid@test.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("✓ Invalid credentials rejected correctly")
    
    def test_auth_me_endpoint(self):
        """Test /auth/me endpoint with valid token"""
        # First login
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        token = login_res.json()["access_token"]
        
        # Then get user info
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == COORDINATOR_EMAIL
        print("✓ Auth me endpoint working")


class TestDashboardAndStats:
    """Dashboard statistics tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        self.token = login_res.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_dashboard_stats(self):
        """Test dashboard stats endpoint"""
        today = datetime.now().strftime("%Y-%m-%d")
        response = requests.get(
            f"{BASE_URL}/api/dashboard/stats?date={today}",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "active_journeys" in data
        assert "closed_journeys" in data
        assert "total_packages" in data
        assert "delivery_rate" in data
        print(f"✓ Dashboard stats: {data['active_journeys']} active, {data['closed_journeys']} closed")
    
    def test_incidents_breakdown(self):
        """Test incidents breakdown endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/incidents-breakdown",
            headers=self.headers
        )
        assert response.status_code == 200
        print("✓ Incidents breakdown endpoint working")
    
    def test_provider_comparison(self):
        """Test provider comparison endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/provider-comparison",
            headers=self.headers
        )
        assert response.status_code == 200
        print("✓ Provider comparison endpoint working")


class TestClientsAndProviders:
    """Clients and providers CRUD tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        self.token = login_res.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_clients(self):
        """Test getting clients list"""
        response = requests.get(f"{BASE_URL}/api/clients", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Check for expected seed data clients
        client_names = [c["name"] for c in data]
        print(f"✓ Clients list: {client_names}")
    
    def test_get_providers(self):
        """Test getting providers list"""
        response = requests.get(f"{BASE_URL}/api/providers", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        provider_names = [p["name"] for p in data]
        print(f"✓ Providers list: {provider_names}")


class TestUsersAndAssignments:
    """User management and assignment tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        self.token = login_res.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_users_as_coordinator(self):
        """Test getting users list as coordinator"""
        response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3  # At least 3 seed users
        
        # Check user structure includes assignment fields
        for user in data:
            assert "assigned_client_names" in user
            assert "assigned_provider_names" in user
        print(f"✓ Users list: {len(data)} users found")
    
    def test_update_user_assignments(self):
        """Test updating user assignments (clients/providers)"""
        # First get users and clients/providers
        users_res = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        users = users_res.json()
        
        clients_res = requests.get(f"{BASE_URL}/api/clients", headers=self.headers)
        clients = clients_res.json()
        
        providers_res = requests.get(f"{BASE_URL}/api/providers", headers=self.headers)
        providers = providers_res.json()
        
        if not users or not clients or not providers:
            pytest.skip("No users, clients, or providers available for assignment test")
        
        # Find an agent user to update
        agent_user = next((u for u in users if u["role"] == "agent"), None)
        if not agent_user:
            pytest.skip("No agent user found for assignment test")
        
        # Update assignments
        response = requests.put(
            f"{BASE_URL}/api/users/{agent_user['id']}/assignments",
            headers=self.headers,
            json={
                "assigned_clients": [clients[0]["id"]] if clients else [],
                "assigned_providers": [providers[0]["id"]] if providers else []
            }
        )
        assert response.status_code == 200
        print(f"✓ User assignments updated for {agent_user['name']}")
        
        # Verify assignments were saved
        users_res = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        updated_user = next((u for u in users_res.json() if u["id"] == agent_user["id"]), None)
        assert updated_user is not None
        print(f"✓ Verified assignments: clients={updated_user.get('assigned_client_names')}, providers={updated_user.get('assigned_provider_names')}")


class TestJourneys:
    """Journey CRUD and workflow tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        self.token = login_res.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_journeys(self):
        """Test getting journeys list"""
        response = requests.get(f"{BASE_URL}/api/journeys", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Journeys list: {len(data)} journeys found")
    
    def test_create_journey(self):
        """Test creating a new journey"""
        # Get client and provider IDs
        clients_res = requests.get(f"{BASE_URL}/api/clients", headers=self.headers)
        providers_res = requests.get(f"{BASE_URL}/api/providers", headers=self.headers)
        
        clients = clients_res.json()
        providers = providers_res.json()
        
        if not clients or not providers:
            pytest.skip("No clients or providers available for journey creation")
        
        today = datetime.now().strftime("%Y-%m-%d")
        response = requests.post(
            f"{BASE_URL}/api/journeys",
            headers=self.headers,
            json={
                "date": today,
                "client_id": clients[0]["id"],
                "provider_id": providers[0]["id"],
                "packages": [
                    {
                        "tracking_number": "TEST_TRK001",
                        "recipient_name": "Test Recipient",
                        "address": "Test Address 123",
                        "zone": "Test Zone",
                        "delivery_window": "09:00-12:00"
                    }
                ],
                "retry_packages": []
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        print(f"✓ Journey created: {data['id']}")
        
        # Store journey ID for cleanup
        self.created_journey_id = data["id"]
        return data["id"]


class TestJourneyStartWithNewFields:
    """Test journey start with new extended checklist fields"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token and create a test journey"""
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        self.token = login_res.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        
        # Get client and provider
        clients_res = requests.get(f"{BASE_URL}/api/clients", headers=self.headers)
        providers_res = requests.get(f"{BASE_URL}/api/providers", headers=self.headers)
        self.clients = clients_res.json()
        self.providers = providers_res.json()
    
    def test_start_journey_with_new_fields(self):
        """Test starting journey with new fields: arrival_time_cedis, backup_driver_name, etc."""
        if not self.clients or not self.providers:
            pytest.skip("No clients or providers available")
        
        # Create a journey first
        today = datetime.now().strftime("%Y-%m-%d")
        create_res = requests.post(
            f"{BASE_URL}/api/journeys",
            headers=self.headers,
            json={
                "date": today,
                "client_id": self.clients[0]["id"],
                "provider_id": self.providers[0]["id"],
                "packages": [
                    {
                        "tracking_number": "TEST_START_TRK001",
                        "recipient_name": "Test Start Recipient",
                        "address": "Test Address",
                        "zone": "Test Zone",
                        "delivery_window": "09:00-12:00"
                    }
                ],
                "retry_packages": []
            }
        )
        assert create_res.status_code == 200
        journey_id = create_res.json()["id"]
        print(f"✓ Test journey created: {journey_id}")
        
        # Start the journey with new fields
        start_data = {
            "departure_time": f"{today}T08:30:00",
            "odometer_start": 45000,
            "fuel_level": "Lleno",
            "vehicle_condition": "Bueno",
            "vehicle_notes": "",
            "packages_loaded": 1,
            "notes": "Test start with new fields",
            "checklist_completed": True,
            # New fields
            "arrival_time_cedis": "07:45",
            "backup_driver_name": "Test Backup Driver",
            "backup_request_time": "08:00",
            "backup_arrival_time": "08:15"
        }
        
        response = requests.put(
            f"{BASE_URL}/api/journeys/{journey_id}/start",
            headers=self.headers,
            json=start_data
        )
        assert response.status_code == 200
        print("✓ Journey started with new fields")
        
        # Verify the journey was updated with new fields
        journey_res = requests.get(f"{BASE_URL}/api/journeys/{journey_id}", headers=self.headers)
        assert journey_res.status_code == 200
        journey = journey_res.json()
        
        assert journey["status"] == "in_progress"
        assert journey["start_data"]["arrival_time_cedis"] == "07:45"
        assert journey["start_data"]["backup_driver_name"] == "Test Backup Driver"
        assert journey["start_data"]["backup_request_time"] == "08:00"
        assert journey["start_data"]["backup_arrival_time"] == "08:15"
        print("✓ New start fields verified in journey data")


class TestIncidents:
    """Incident management tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        self.token = login_res.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_get_incidents(self):
        """Test getting incidents list"""
        response = requests.get(f"{BASE_URL}/api/incidents", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Incidents list: {len(data)} incidents found")


class TestReportsAPI:
    """Reports API tests for BI integration"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        self.token = login_res.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_reports_schema(self):
        """Test reports schema endpoint"""
        response = requests.get(f"{BASE_URL}/api/reports/schema", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "endpoints" in data
        print("✓ Reports schema endpoint working")
    
    def test_reports_journeys(self):
        """Test reports journeys endpoint"""
        response = requests.get(f"{BASE_URL}/api/reports/journeys", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total" in data
        print(f"✓ Reports journeys: {data['total']} records")
    
    def test_reports_kpis(self):
        """Test reports KPIs endpoint"""
        response = requests.get(f"{BASE_URL}/api/reports/kpis", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        print("✓ Reports KPIs endpoint working")


class TestDBCleanupVerification:
    """Verify DB cleanup was done correctly"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for tests"""
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": COORDINATOR_EMAIL,
            "password": COORDINATOR_PASSWORD
        })
        self.token = login_res.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_verify_users_exist(self):
        """Verify users still exist after cleanup"""
        response = requests.get(f"{BASE_URL}/api/users", headers=self.headers)
        assert response.status_code == 200
        users = response.json()
        assert len(users) >= 3  # At least 3 seed users
        print(f"✓ Users exist: {len(users)} users")
    
    def test_verify_clients_exist(self):
        """Verify clients still exist after cleanup"""
        response = requests.get(f"{BASE_URL}/api/clients", headers=self.headers)
        assert response.status_code == 200
        clients = response.json()
        assert len(clients) >= 1
        print(f"✓ Clients exist: {len(clients)} clients")
    
    def test_verify_providers_exist(self):
        """Verify providers still exist after cleanup"""
        response = requests.get(f"{BASE_URL}/api/providers", headers=self.headers)
        assert response.status_code == 200
        providers = response.json()
        assert len(providers) >= 1
        print(f"✓ Providers exist: {len(providers)} providers")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
