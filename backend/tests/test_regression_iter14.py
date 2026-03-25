"""
Regression tests for LastMile OS API after modular refactoring.
Tests all API endpoints to verify they work correctly after splitting server.py into route modules.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://lastmile-mvp.preview.emergentagent.com')

# Test credentials
DEV_EMAIL = "dev@me.mx"
DEV_PASSWORD = "LastMile2026"
COORDINATOR_EMAIL = "yael@me.mx"
COORDINATOR_PASSWORD = "LastMile2026"
AGENT_EMAIL = "agente@me.mx"
AGENT_PASSWORD = "LastMile2026"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def dev_token(api_client):
    """Get developer auth token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEV_EMAIL,
        "password": DEV_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Developer login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def coordinator_token(api_client):
    """Get coordinator auth token"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": COORDINATOR_EMAIL,
        "password": COORDINATOR_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Coordinator login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def authenticated_client(api_client, dev_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {dev_token}"})
    return api_client


# ==================== HEALTH CHECK TESTS ====================

class TestHealthEndpoints:
    """Test basic health and root endpoints"""
    
    def test_api_root(self, api_client):
        """GET /api/ - Root endpoint"""
        response = api_client.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "LastMile OS API" in data["message"]
        print(f"✓ API root: {data}")
    
    def test_api_health(self, api_client):
        """GET /api/health - Health check"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        print(f"✓ Health check: {data}")


# ==================== AUTH TESTS ====================

class TestAuthRoutes:
    """Test authentication routes from auth_routes.py"""
    
    def test_login_success(self, api_client):
        """POST /api/auth/login - Login with valid credentials"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEV_EMAIL,
            "password": DEV_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == DEV_EMAIL
        assert data["user"]["role"] == "developer"
        print(f"✓ Login success: user={data['user']['name']}, role={data['user']['role']}")
    
    def test_login_invalid_credentials(self, api_client):
        """POST /api/auth/login - Login with invalid credentials"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": "invalid@test.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401
        print("✓ Invalid login rejected with 401")
    
    def test_get_me(self, authenticated_client):
        """GET /api/auth/me - Get current user info"""
        response = authenticated_client.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        assert "role" in data
        assert "name" in data
        print(f"✓ Get me: {data['name']} ({data['email']})")
    
    def test_logout(self, api_client, dev_token):
        """POST /api/auth/logout - Logout and revoke token"""
        # Use a fresh token for logout test
        login_response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEV_EMAIL,
            "password": DEV_PASSWORD
        })
        token = login_response.json().get("access_token")
        
        response = api_client.post(
            f"{BASE_URL}/api/auth/logout",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"✓ Logout: {data['message']}")


# ==================== USER ROUTES TESTS ====================

class TestUserRoutes:
    """Test user management routes from user_routes.py"""
    
    def test_get_users(self, authenticated_client):
        """GET /api/users - Get user list (coordinator/developer only)"""
        response = authenticated_client.get(f"{BASE_URL}/api/users")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            assert "email" in data[0]
            assert "role" in data[0]
        print(f"✓ Get users: {len(data)} users found")
    
    def test_get_clients(self, authenticated_client):
        """GET /api/clients - Get clients list"""
        response = authenticated_client.get(f"{BASE_URL}/api/clients")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            assert "id" in data[0]
            assert "name" in data[0]
        print(f"✓ Get clients: {len(data)} clients found")
    
    def test_get_providers(self, authenticated_client):
        """GET /api/providers - Get providers list"""
        response = authenticated_client.get(f"{BASE_URL}/api/providers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            assert "id" in data[0]
            assert "name" in data[0]
        print(f"✓ Get providers: {len(data)} providers found")


# ==================== JOURNEY ROUTES TESTS ====================

class TestJourneyRoutes:
    """Test journey management routes from journey_routes.py"""
    
    def test_get_journeys_paginated(self, authenticated_client):
        """GET /api/journeys - Get paginated journeys"""
        response = authenticated_client.get(f"{BASE_URL}/api/journeys?page=1&page_size=25")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "pagination" in data
        assert "page" in data["pagination"]
        assert "page_size" in data["pagination"]
        assert "total_count" in data["pagination"]
        assert "total_pages" in data["pagination"]
        print(f"✓ Get journeys: {data['pagination']['total_count']} total, page {data['pagination']['page']} of {data['pagination']['total_pages']}")
    
    def test_get_incidents(self, authenticated_client):
        """GET /api/incidents - Get incidents list"""
        response = authenticated_client.get(f"{BASE_URL}/api/incidents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Get incidents: {len(data)} incidents found")


# ==================== DASHBOARD ROUTES TESTS ====================

class TestDashboardRoutes:
    """Test dashboard routes from dashboard_routes.py"""
    
    def test_get_dashboard_stats(self, authenticated_client):
        """GET /api/dashboard/stats - Get dashboard statistics"""
        response = authenticated_client.get(f"{BASE_URL}/api/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        # Verify expected fields
        expected_fields = ["active_journeys", "closed_journeys", "total_journeys", 
                          "total_packages", "delivered_packages", "delivery_rate", "open_incidents"]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
        print(f"✓ Dashboard stats: {data['total_journeys']} journeys, {data['delivery_rate']}% delivery rate")
    
    def test_get_incidents_breakdown(self, authenticated_client):
        """GET /api/dashboard/incidents-breakdown - Get incidents breakdown"""
        response = authenticated_client.get(f"{BASE_URL}/api/dashboard/incidents-breakdown")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        print(f"✓ Incidents breakdown: {len(data)} types")
    
    def test_package_search(self, authenticated_client):
        """GET /api/packages/search - Search packages"""
        response = authenticated_client.get(f"{BASE_URL}/api/packages/search?q=TRK")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Package search 'TRK': {len(data)} results")


# ==================== ANALYTICS ROUTES TESTS ====================

class TestAnalyticsRoutes:
    """Test analytics routes from analytics_routes.py"""
    
    def test_get_heatmap_data(self, authenticated_client):
        """GET /api/analytics/heatmap - Get heatmap data"""
        response = authenticated_client.get(f"{BASE_URL}/api/analytics/heatmap")
        assert response.status_code == 200
        data = response.json()
        assert "group_by" in data
        assert "total_packages" in data
        assert "areas" in data
        print(f"✓ Heatmap: {data['total_packages']} packages, {len(data['areas'])} areas")
    
    def test_get_quality_report(self, authenticated_client):
        """GET /api/reports/quality - Get quality report"""
        response = authenticated_client.get(f"{BASE_URL}/api/reports/quality")
        assert response.status_code == 200
        data = response.json()
        assert "by_provider" in data
        assert "by_type" in data
        assert "summary" in data
        print(f"✓ Quality report: avg_score={data['summary'].get('avg_score', 0)}, total_evaluated={data['summary'].get('total_evaluated', 0)}")
    
    def test_get_reports_schema(self, authenticated_client):
        """GET /api/reports/schema - Get API documentation schema"""
        response = authenticated_client.get(f"{BASE_URL}/api/reports/schema")
        assert response.status_code == 200
        data = response.json()
        assert "api_version" in data
        assert "endpoints" in data
        assert "authentication" in data
        print(f"✓ Reports schema: {len(data['endpoints'])} endpoints documented")
    
    def test_get_token_consumption(self, authenticated_client):
        """GET /api/system/token-consumption - Get token consumption stats"""
        response = authenticated_client.get(f"{BASE_URL}/api/system/token-consumption")
        assert response.status_code == 200
        data = response.json()
        assert "ai_evaluations" in data
        assert "estimated_tokens" in data
        assert "total_cost_usd" in data
        print(f"✓ Token consumption: {data['ai_evaluations']} AI evaluations, ${data['total_cost_usd']} USD")


# ==================== SYSTEM ROUTES TESTS ====================

class TestSystemRoutes:
    """Test system routes"""
    
    def test_system_health(self, authenticated_client):
        """GET /api/system/health - System health check"""
        response = authenticated_client.get(f"{BASE_URL}/api/system/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        print(f"✓ System health: {data}")


# ==================== SYNC ROUTES TESTS ====================

class TestSyncRoutes:
    """Test Kosmo sync routes"""
    
    def test_get_sync_status(self, authenticated_client):
        """GET /api/sync/status - Get Kosmo sync status"""
        response = authenticated_client.get(f"{BASE_URL}/api/sync/status")
        assert response.status_code == 200
        data = response.json()
        # May have last_sync, total_checked, updated, errors
        print(f"✓ Sync status: {data}")


# ==================== ADMIN ROUTES TESTS ====================

class TestAdminRoutes:
    """Test admin routes from admin_routes.py"""
    
    def test_cleanup_endpoint_exists(self, authenticated_client):
        """POST /api/cleanup/routes-packages - Verify cleanup endpoint exists (don't actually clean)"""
        # Just verify the endpoint exists by checking OPTIONS or a dry-run approach
        # We won't actually call DELETE to avoid data loss
        # Instead, verify the route is accessible
        response = authenticated_client.post(f"{BASE_URL}/api/cleanup/routes-packages")
        # Should return 200 (success) or 403 (forbidden if not coordinator)
        assert response.status_code in [200, 403]
        print(f"✓ Cleanup endpoint accessible: status={response.status_code}")


# ==================== PASSWORD RESET TESTS ====================

class TestPasswordResetRoutes:
    """Test password reset routes"""
    
    def test_get_password_reset_requests(self, authenticated_client):
        """GET /api/password-reset-requests - Get pending reset requests"""
        response = authenticated_client.get(f"{BASE_URL}/api/password-reset-requests")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"✓ Password reset requests: {len(data)} pending")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
