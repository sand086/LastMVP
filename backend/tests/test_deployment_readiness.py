"""
Test suite for LastMile OS deployment readiness fixes (Iteration 8)
Tests:
- Login flow for all 4 user roles
- GET /api/journeys endpoint (N+1 query optimization)
- POST /api/cleanup/routes-packages endpoint
- GET /api/health endpoint
- Dashboard stats endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_USERS = [
    {"email": "dev@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026"), "role": "developer"},
    {"email": "agente@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026"), "role": "agent"},
    {"email": "yael@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026"), "role": "coordinator"},
    {"email": "karina@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026"), "role": "executive"},
]


class TestHealthEndpoint:
    """Health check endpoint tests"""
    
    def test_health_returns_healthy(self):
        """GET /api/health should return healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        print(f"✓ Health endpoint returns: {data}")


class TestLoginFlow:
    """Login flow tests for all 4 user roles"""
    
    @pytest.mark.parametrize("user", TEST_USERS)
    def test_login_all_roles(self, user):
        """Test login works for all 4 user roles"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": user["email"], "password": user["password"]}
        )
        assert response.status_code == 200, f"Login failed for {user['email']}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "access_token" in data, "Response missing access_token"
        assert "user" in data, "Response missing user object"
        assert data["user"]["email"] == user["email"]
        assert data["user"]["role"] == user["role"]
        assert len(data["access_token"]) > 0
        print(f"✓ Login successful for {user['email']} (role: {user['role']})")
    
    def test_login_invalid_credentials(self):
        """Test login fails with invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "invalid@test.com", "password": "wrongpassword"}
        )
        assert response.status_code == 401
        print("✓ Invalid credentials correctly rejected")


class TestJourneysEndpoint:
    """Tests for GET /api/journeys endpoint with N+1 query optimization"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for developer user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "dev@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        pytest.skip("Authentication failed")
    
    def test_journeys_returns_array(self, auth_token):
        """GET /api/journeys should return array (even empty)"""
        response = requests.get(
            f"{BASE_URL}/api/journeys",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Response should be an array"
        print(f"✓ Journeys endpoint returns array with {len(data)} items")
    
    def test_journeys_with_date_filter(self, auth_token):
        """GET /api/journeys with date filters should work"""
        response = requests.get(
            f"{BASE_URL}/api/journeys",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Journeys with date filter returns {len(data)} items")
    
    def test_journeys_with_status_filter(self, auth_token):
        """GET /api/journeys with status filter should work"""
        for status in ["scheduled", "in_progress", "closed"]:
            response = requests.get(
                f"{BASE_URL}/api/journeys",
                params={"status": status},
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            print(f"✓ Journeys with status={status} returns {len(data)} items")
    
    def test_journeys_unauthorized(self):
        """GET /api/journeys without auth should fail"""
        response = requests.get(f"{BASE_URL}/api/journeys")
        assert response.status_code in [401, 403]
        print("✓ Journeys endpoint correctly requires authentication")


class TestCleanupEndpoint:
    """Tests for POST /api/cleanup/routes-packages endpoint"""
    
    @pytest.fixture
    def coordinator_token(self):
        """Get auth token for coordinator user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "yael@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        pytest.skip("Authentication failed")
    
    @pytest.fixture
    def developer_token(self):
        """Get auth token for developer user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "dev@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        pytest.skip("Authentication failed")
    
    @pytest.fixture
    def agent_token(self):
        """Get auth token for agent user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "agente@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        pytest.skip("Authentication failed")
    
    def test_cleanup_coordinator_access(self, coordinator_token):
        """POST /api/cleanup/routes-packages should work for coordinator"""
        response = requests.post(
            f"{BASE_URL}/api/cleanup/routes-packages",
            headers={"Authorization": f"Bearer {coordinator_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "deleted" in data
        assert "journeys" in data["deleted"]
        assert "packages" in data["deleted"]
        assert "incidents" in data["deleted"]
        print(f"✓ Cleanup works for coordinator: {data}")
    
    def test_cleanup_developer_access(self, developer_token):
        """POST /api/cleanup/routes-packages should work for developer"""
        response = requests.post(
            f"{BASE_URL}/api/cleanup/routes-packages",
            headers={"Authorization": f"Bearer {developer_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"✓ Cleanup works for developer: {data}")
    
    def test_cleanup_agent_denied(self, agent_token):
        """POST /api/cleanup/routes-packages should be denied for agent"""
        response = requests.post(
            f"{BASE_URL}/api/cleanup/routes-packages",
            headers={"Authorization": f"Bearer {agent_token}"}
        )
        assert response.status_code == 403
        print("✓ Cleanup correctly denied for agent role")


class TestDashboardStats:
    """Tests for dashboard stats endpoint"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for developer user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "dev@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        pytest.skip("Authentication failed")
    
    def test_dashboard_stats(self, auth_token):
        """GET /api/dashboard/stats should return stats object"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/stats",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify expected fields
        expected_fields = [
            "date", "active_journeys", "closed_journeys", "total_journeys",
            "total_packages", "delivered_packages", "delivery_rate",
            "open_incidents", "total_km"
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        
        print(f"✓ Dashboard stats: {data}")
    
    def test_dashboard_stats_with_date(self, auth_token):
        """GET /api/dashboard/stats with date param should work"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/stats",
            params={"date": "2026-03-23"},
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["date"] == "2026-03-23"
        print("✓ Dashboard stats with date filter works")


class TestAuthMe:
    """Tests for GET /api/auth/me endpoint"""
    
    def test_auth_me_returns_user(self):
        """GET /api/auth/me should return current user"""
        # Login first
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "dev@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
        )
        token = login_response.json()["access_token"]
        
        # Get current user
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "dev@me.mx"
        assert data["role"] == "developer"
        assert "password" not in data  # Password should not be returned
        print(f"✓ Auth/me returns user: {data['email']} ({data['role']})")


class TestClientsProviders:
    """Tests for clients and providers endpoints"""
    
    @pytest.fixture
    def auth_token(self):
        """Get auth token for developer user"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "dev@me.mx", "password": os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")}
        )
        if response.status_code == 200:
            return response.json()["access_token"]
        pytest.skip("Authentication failed")
    
    def test_get_clients(self, auth_token):
        """GET /api/clients should return array"""
        response = requests.get(
            f"{BASE_URL}/api/clients",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Clients endpoint returns {len(data)} clients")
    
    def test_get_providers(self, auth_token):
        """GET /api/providers should return array"""
        response = requests.get(
            f"{BASE_URL}/api/providers",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Providers endpoint returns {len(data)} providers")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
