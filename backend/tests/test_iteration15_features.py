"""
Iteration 15 Test Suite - Testing batch-rescrape, rescrape, quality criteria, and core APIs
Tests for LastMile OS MVP features including:
- Authentication (login with valid/invalid credentials)
- Journeys listing with pagination
- Journey detail with packages and incidents
- Batch rescrape endpoint (new feature)
- Individual package rescrape
- Quality criteria endpoint
- Dashboard stats
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEV_EMAIL = "dev@me.mx"
DEV_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
AGENT_EMAIL = "agente@me.mx"
AGENT_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")
INVALID_EMAIL = "invalid@test.com"
INVALID_PASSWORD = "wrongpassword"

# Known journey ID with packages needing rescrape
KNOWN_JOURNEY_ID = "5ff66c70-b12a-48ad-9dd7-39713caa99fe"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token for developer user"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEV_EMAIL,
        "password": DEV_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


class TestHealthCheck:
    """Health check endpoint tests - run first"""
    
    def test_health_endpoint(self, api_client):
        """Test /api/health returns healthy status"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        assert "timestamp" in data


class TestAuthentication:
    """Authentication endpoint tests"""
    
    def test_login_success_developer(self, api_client):
        """Test login with valid developer credentials"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEV_EMAIL,
            "password": DEV_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == DEV_EMAIL
        assert data["user"]["role"] == "developer"
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0
    
    def test_login_success_agent(self, api_client):
        """Test login with valid agent credentials"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": AGENT_EMAIL,
            "password": AGENT_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        
        assert "access_token" in data
        assert data["user"]["email"] == AGENT_EMAIL
        assert data["user"]["role"] == "agent"
    
    def test_login_invalid_credentials(self, api_client):
        """Test login with invalid credentials returns 401"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": INVALID_EMAIL,
            "password": INVALID_PASSWORD
        })
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
    
    def test_login_wrong_password(self, api_client):
        """Test login with wrong password returns 401"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEV_EMAIL,
            "password": "wrongpassword"
        })
        assert response.status_code == 401
    
    def test_get_current_user(self, authenticated_client):
        """Test /api/auth/me returns current user info"""
        response = authenticated_client.get(f"{BASE_URL}/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == DEV_EMAIL
        assert "id" in data
        assert "role" in data


class TestJourneys:
    """Journey endpoints tests"""
    
    def test_get_journeys_list(self, authenticated_client):
        """Test GET /api/journeys returns paginated list"""
        response = authenticated_client.get(f"{BASE_URL}/api/journeys", params={
            "page": 1,
            "page_size": 10
        })
        assert response.status_code == 200
        data = response.json()
        
        # Verify pagination structure
        assert "data" in data
        assert "pagination" in data
        assert isinstance(data["data"], list)
        assert "page" in data["pagination"]
        assert "page_size" in data["pagination"]
        assert "total_count" in data["pagination"]
        assert "total_pages" in data["pagination"]
    
    def test_get_journeys_with_date_filter(self, authenticated_client):
        """Test GET /api/journeys with date filters"""
        response = authenticated_client.get(f"{BASE_URL}/api/journeys", params={
            "date_from": "2026-03-23",
            "date_to": "2026-03-25",
            "page": 1,
            "page_size": 25
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
    
    def test_get_journey_detail(self, authenticated_client):
        """Test GET /api/journeys/{journey_id} returns journey with packages"""
        response = authenticated_client.get(f"{BASE_URL}/api/journeys/{KNOWN_JOURNEY_ID}")
        assert response.status_code == 200
        data = response.json()
        
        # Verify journey structure
        assert data["id"] == KNOWN_JOURNEY_ID
        assert "date" in data
        assert "status" in data
        assert "packages" in data
        assert "incidents" in data
        assert isinstance(data["packages"], list)
        assert len(data["packages"]) > 0  # Known journey has 61 packages
        
        # Verify package structure
        if data["packages"]:
            pkg = data["packages"][0]
            assert "id" in pkg
            assert "status" in pkg
    
    def test_get_journey_not_found(self, authenticated_client):
        """Test GET /api/journeys/{invalid_id} returns 404"""
        response = authenticated_client.get(f"{BASE_URL}/api/journeys/invalid-journey-id-12345")
        assert response.status_code == 404


class TestBatchRescrape:
    """Batch rescrape endpoint tests - NEW FEATURE"""
    
    def test_batch_rescrape_journey(self, authenticated_client):
        """Test POST /api/journeys/{journey_id}/batch-rescrape"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/journeys/{KNOWN_JOURNEY_ID}/batch-rescrape",
            timeout=120
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "total" in data
        assert "recovered" in data
        assert "errors" in data
        assert "message" in data
        
        # Verify data types
        assert isinstance(data["total"], int)
        assert isinstance(data["recovered"], int)
        assert isinstance(data["errors"], int)
        assert isinstance(data["message"], str)
    
    def test_batch_rescrape_invalid_journey(self, authenticated_client):
        """Test batch rescrape with invalid journey ID returns 404"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/journeys/invalid-journey-id/batch-rescrape",
            timeout=30
        )
        assert response.status_code == 404


class TestPackageRescrape:
    """Individual package rescrape endpoint tests"""
    
    def test_rescrape_package_with_tracking_url(self, authenticated_client):
        """Test POST /api/packages/{package_id}/rescrape for package with tracking URL"""
        # First get a package with tracking_url from the known journey
        journey_response = authenticated_client.get(f"{BASE_URL}/api/journeys/{KNOWN_JOURNEY_ID}")
        assert journey_response.status_code == 200
        
        packages = journey_response.json().get("packages", [])
        package_with_url = next(
            (p for p in packages if p.get("tracking_url")),
            None
        )
        
        if not package_with_url:
            pytest.skip("No package with tracking_url found")
        
        package_id = package_with_url["id"]
        
        # Test rescrape
        response = authenticated_client.post(
            f"{BASE_URL}/api/packages/{package_id}/rescrape",
            timeout=60
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "success" in data
        assert data["success"]
        assert "kosmo_status" in data
        assert "proof_count" in data
    
    def test_rescrape_package_not_found(self, authenticated_client):
        """Test rescrape with invalid package ID returns 404"""
        response = authenticated_client.post(
            f"{BASE_URL}/api/packages/invalid-package-id/rescrape",
            timeout=30
        )
        assert response.status_code == 404


class TestQualityCriteria:
    """Quality criteria endpoint tests"""
    
    def test_get_quality_criteria(self, authenticated_client):
        """Test GET /api/quality/criteria returns criteria configuration"""
        response = authenticated_client.get(f"{BASE_URL}/api/quality/criteria")
        assert response.status_code == 200
        data = response.json()
        
        # Verify expected keys
        assert "delivery_types" in data
        assert "ai_evaluation" in data
        assert "version" in data


class TestDashboardStats:
    """Dashboard statistics endpoint tests"""
    
    def test_get_dashboard_stats(self, authenticated_client):
        """Test GET /api/dashboard/stats returns statistics"""
        response = authenticated_client.get(f"{BASE_URL}/api/dashboard/stats", params={
            "date_from": "2026-03-23",
            "date_to": "2026-03-25"
        })
        assert response.status_code == 200
        data = response.json()
        
        # Verify expected fields
        assert "total_journeys" in data
        assert "total_packages" in data
        assert "delivered_packages" in data
        assert "delivery_rate" in data
        assert "open_incidents" in data
    
    def test_get_dashboard_stats_default_date(self, authenticated_client):
        """Test GET /api/dashboard/stats without date params uses today"""
        response = authenticated_client.get(f"{BASE_URL}/api/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_journeys" in data


class TestIncidents:
    """Incidents endpoint tests"""
    
    def test_get_incidents_list(self, authenticated_client):
        """Test GET /api/incidents returns list"""
        response = authenticated_client.get(f"{BASE_URL}/api/incidents")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_get_incidents_by_journey(self, authenticated_client):
        """Test GET /api/incidents with journey_id filter"""
        response = authenticated_client.get(f"{BASE_URL}/api/incidents", params={
            "journey_id": KNOWN_JOURNEY_ID
        })
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
