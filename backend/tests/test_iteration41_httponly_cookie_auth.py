"""
Iteration 41 - Testing httpOnly Cookie Auth Migration and Component Refactoring

Tests:
1. Login sets httpOnly cookie (lm_access_token)
2. GET /api/auth/me works with cookie (no Bearer header needed)
3. GET /api/auth/me works with Bearer header (backward compatibility)
4. Logout clears the cookie
5. 401 without auth
6. Kosmo sync status includes rate_limited field
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_CREDENTIALS = {
    "developer": {"email": "dev@me.mx", "password": "LastMile2026"},
    "coordinator": {"email": "yael@me.mx", "password": "LastMile2026"},
    "agent": {"email": "agente@me.mx", "password": "LastMile2026"},
}


class TestHealthCheck:
    """Basic health check to ensure API is running"""
    
    def test_health_endpoint(self):
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✓ Health check passed")


class TestHttpOnlyCookieAuth:
    """Test httpOnly cookie authentication flow"""
    
    def test_login_sets_cookie(self):
        """POST /api/auth/login should return Set-Cookie header with lm_access_token"""
        session = requests.Session()
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json=TEST_CREDENTIALS["developer"]
        )
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        
        # Check response body contains token and user
        data = response.json()
        assert "access_token" in data, "Response should contain access_token"
        assert "user" in data, "Response should contain user"
        assert data["user"]["email"] == TEST_CREDENTIALS["developer"]["email"]
        
        # Check Set-Cookie header
        cookies = response.cookies
        assert "lm_access_token" in cookies, "Cookie lm_access_token should be set"
        
        # Verify cookie attributes from Set-Cookie header
        set_cookie_header = response.headers.get("Set-Cookie", "")
        assert "lm_access_token=" in set_cookie_header, "Set-Cookie header should contain lm_access_token"
        assert "httponly" in set_cookie_header.lower(), "Cookie should be httpOnly"
        assert "path=/api" in set_cookie_header.lower(), "Cookie path should be /api"
        # Note: Secure and SameSite may not appear in all environments
        
        print("✓ Login sets httpOnly cookie correctly")
        return session, data["access_token"]
    
    def test_auth_me_with_cookie(self):
        """GET /api/auth/me should work with cookie (no Bearer header needed)"""
        # First login to get cookie
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json=TEST_CREDENTIALS["developer"]
        )
        assert login_response.status_code == 200
        
        # Now call /auth/me using only the cookie (no Authorization header)
        me_response = session.get(f"{BASE_URL}/api/auth/me")
        
        assert me_response.status_code == 200, f"Auth/me with cookie failed: {me_response.text}"
        data = me_response.json()
        assert data["email"] == TEST_CREDENTIALS["developer"]["email"]
        assert data["role"] == "developer"
        
        print("✓ GET /api/auth/me works with cookie authentication")
    
    def test_auth_me_with_bearer_header(self):
        """GET /api/auth/me should still work with Authorization: Bearer header (backward compat)"""
        # Login to get token
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json=TEST_CREDENTIALS["coordinator"]
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]
        
        # Create new session without cookies, use Bearer header
        new_session = requests.Session()
        new_session.headers.update({"Authorization": f"Bearer {token}"})
        
        me_response = new_session.get(f"{BASE_URL}/api/auth/me")
        
        assert me_response.status_code == 200, f"Auth/me with Bearer failed: {me_response.text}"
        data = me_response.json()
        assert data["email"] == TEST_CREDENTIALS["coordinator"]["email"]
        assert data["role"] == "coordinator"
        
        print("✓ GET /api/auth/me works with Bearer header (backward compatibility)")
    
    def test_logout_clears_cookie(self):
        """POST /api/auth/logout should clear the lm_access_token cookie"""
        # First login
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json=TEST_CREDENTIALS["agent"]
        )
        assert login_response.status_code == 200
        
        # Verify cookie is set
        assert "lm_access_token" in session.cookies
        
        # Logout
        logout_response = session.post(f"{BASE_URL}/api/auth/logout")
        assert logout_response.status_code == 200
        
        data = logout_response.json()
        assert "message" in data
        
        # Check Set-Cookie header clears the cookie
        set_cookie_header = logout_response.headers.get("Set-Cookie", "")
        # Cookie should be deleted (max-age=0 or expires in past)
        assert "lm_access_token=" in set_cookie_header, "Logout should set cookie header to clear it"
        
        print("✓ Logout clears the cookie correctly")
    
    def test_401_without_auth(self):
        """GET /api/auth/me without cookie or header should return 401"""
        # Fresh session with no auth
        session = requests.Session()
        response = session.get(f"{BASE_URL}/api/auth/me")
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        data = response.json()
        assert "detail" in data
        
        print("✓ 401 returned when no authentication provided")
    
    def test_cookie_priority_over_bearer(self):
        """When both cookie and Bearer header present, cookie should be used first"""
        # Login as developer to get cookie
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json=TEST_CREDENTIALS["developer"]
        )
        assert login_response.status_code == 200
        
        # Login as coordinator to get different token
        coord_login = requests.post(
            f"{BASE_URL}/api/auth/login",
            json=TEST_CREDENTIALS["coordinator"]
        )
        coord_token = coord_login.json()["access_token"]
        
        # Use developer's cookie session but add coordinator's Bearer header
        session.headers.update({"Authorization": f"Bearer {coord_token}"})
        
        # The cookie should take priority (developer user)
        me_response = session.get(f"{BASE_URL}/api/auth/me")
        assert me_response.status_code == 200
        data = me_response.json()
        
        # Should be developer (from cookie), not coordinator (from Bearer)
        assert data["email"] == TEST_CREDENTIALS["developer"]["email"]
        
        print("✓ Cookie takes priority over Bearer header")


class TestKosmoSyncStatus:
    """Test Kosmo sync status endpoint includes rate_limited field"""
    
    def test_sync_status_includes_rate_limited(self):
        """GET /api/sync/status should include rate_limited field"""
        # Login first
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json=TEST_CREDENTIALS["developer"]
        )
        assert login_response.status_code == 200
        
        # Get sync status
        response = session.get(f"{BASE_URL}/api/sync/status")
        assert response.status_code == 200, f"Sync status failed: {response.text}"
        
        data = response.json()
        assert "rate_limited" in data, "Response should include rate_limited field"
        assert isinstance(data["rate_limited"], bool), "rate_limited should be boolean"
        
        print(f"✓ Sync status includes rate_limited field: {data['rate_limited']}")


class TestProtectedEndpointsWithCookie:
    """Test that protected endpoints work with cookie auth"""
    
    def test_get_users_with_cookie(self):
        """GET /api/users should work with cookie auth"""
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json=TEST_CREDENTIALS["coordinator"]
        )
        assert login_response.status_code == 200
        
        response = session.get(f"{BASE_URL}/api/users")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        print(f"✓ GET /api/users works with cookie auth ({len(data)} users)")
    
    def test_get_clients_with_cookie(self):
        """GET /api/clients should work with cookie auth"""
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json=TEST_CREDENTIALS["developer"]
        )
        assert login_response.status_code == 200
        
        response = session.get(f"{BASE_URL}/api/clients")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        print(f"✓ GET /api/clients works with cookie auth ({len(data)} clients)")
    
    def test_get_providers_with_cookie(self):
        """GET /api/providers should work with cookie auth"""
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json=TEST_CREDENTIALS["developer"]
        )
        assert login_response.status_code == 200
        
        response = session.get(f"{BASE_URL}/api/providers")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        print(f"✓ GET /api/providers works with cookie auth ({len(data)} providers)")
    
    def test_get_journeys_with_cookie(self):
        """GET /api/journeys should work with cookie auth"""
        session = requests.Session()
        login_response = session.post(
            f"{BASE_URL}/api/auth/login",
            json=TEST_CREDENTIALS["agent"]
        )
        assert login_response.status_code == 200
        
        response = session.get(f"{BASE_URL}/api/journeys")
        assert response.status_code == 200
        data = response.json()
        # API returns {data: [...], pagination: {...}}
        assert "data" in data or isinstance(data, list)
        
        print("✓ GET /api/journeys works with cookie auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
