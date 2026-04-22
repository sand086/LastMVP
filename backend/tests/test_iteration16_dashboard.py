"""
Iteration 16 Tests: Dashboard Redesign & Heatmap Features
- GET /api/reports/heatmap - Geo-enriched heatmap data with CP coordinates
- GET /api/dashboard/provider-comparison - Provider comparison with visit_rate
- GET /api/dashboard/stats - Dashboard KPIs
- POST /api/auth/login - Authentication
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "dev@me.mx"
TEST_PASSWORD = os.environ.get("TEST_DEV_PASSWORD", "LastMile2026")

# Date range with existing data
DATE_FROM = "2026-03-01"
DATE_TO = "2026-03-31"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "access_token" in data, "Response missing access_token"
    return data["access_token"]


@pytest.fixture
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestAuthentication:
    """Authentication endpoint tests"""
    
    def test_login_success(self):
        """Test successful login returns access_token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "user" in data
        assert data["user"]["email"] == TEST_EMAIL
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "wrong@example.com", "password": "wrongpass"}
        )
        assert response.status_code == 401


class TestHeatmapEndpoint:
    """Tests for GET /api/reports/heatmap - New geo-enriched heatmap endpoint"""
    
    def test_heatmap_returns_array(self, auth_headers):
        """Heatmap endpoint returns array of CP data points"""
        response = requests.get(
            f"{BASE_URL}/api/reports/heatmap",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list), "Heatmap should return an array"
    
    def test_heatmap_data_structure(self, auth_headers):
        """Each heatmap point has required fields: cp, zone, lat, lng, delivered, failed, total, rate"""
        response = requests.get(
            f"{BASE_URL}/api/reports/heatmap",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            point = data[0]
            required_fields = ["cp", "zone", "lat", "lng", "delivered", "failed", "total", "rate"]
            for field in required_fields:
                assert field in point, f"Missing field: {field}"
            
            # Validate data types
            assert isinstance(point["cp"], str)
            assert isinstance(point["zone"], str)
            assert isinstance(point["lat"], (int, float))
            assert isinstance(point["lng"], (int, float))
            assert isinstance(point["delivered"], int)
            assert isinstance(point["failed"], int)
            assert isinstance(point["total"], int)
            assert isinstance(point["rate"], (int, float))
            
            # Validate coordinate ranges (Mexico)
            assert 14 <= point["lat"] <= 33, f"Latitude {point['lat']} out of Mexico range"
            assert -118 <= point["lng"] <= -86, f"Longitude {point['lng']} out of Mexico range"
    
    def test_heatmap_returns_data_for_date_range(self, auth_headers):
        """Heatmap returns data points for the specified date range"""
        response = requests.get(
            f"{BASE_URL}/api/reports/heatmap",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        # Based on test data, should return 14 points
        assert len(data) >= 10, f"Expected at least 10 data points, got {len(data)}"
    
    def test_heatmap_rate_calculation(self, auth_headers):
        """Rate is correctly calculated as delivered/total"""
        response = requests.get(
            f"{BASE_URL}/api/reports/heatmap",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        for point in data:
            if point["total"] > 0:
                expected_rate = round(point["delivered"] / point["total"], 3)
                assert abs(point["rate"] - expected_rate) < 0.01, \
                    f"Rate mismatch for CP {point['cp']}: expected {expected_rate}, got {point['rate']}"
    
    def test_heatmap_requires_auth(self):
        """Heatmap endpoint requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/reports/heatmap",
            params={"date_from": DATE_FROM, "date_to": DATE_TO}
        )
        # 401 or 403 both indicate auth required
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


class TestProviderComparison:
    """Tests for GET /api/dashboard/provider-comparison with visit_rate"""
    
    def test_provider_comparison_returns_array(self, auth_headers):
        """Provider comparison returns array of providers"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/provider-comparison",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_provider_comparison_has_visit_rate(self, auth_headers):
        """Each provider has visit_rate field (NEW feature)"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/provider-comparison",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            provider = data[0]
            assert "visit_rate" in provider, "Provider missing visit_rate field"
            assert isinstance(provider["visit_rate"], (int, float))
            assert 0 <= provider["visit_rate"] <= 100, "visit_rate should be 0-100"
    
    def test_provider_comparison_data_structure(self, auth_headers):
        """Provider comparison has all required fields"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/provider-comparison",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            provider = data[0]
            required_fields = [
                "provider_id", "provider_name", "journeys_count",
                "avg_delivery_rate", "visit_rate", "total_incidents", "total_km"
            ]
            for field in required_fields:
                assert field in provider, f"Missing field: {field}"


class TestDashboardStats:
    """Tests for GET /api/dashboard/stats - Dashboard KPIs"""
    
    def test_dashboard_stats_returns_kpis(self, auth_headers):
        """Dashboard stats returns all required KPI fields"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/stats",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        required_fields = [
            "active_journeys", "closed_journeys", "total_journeys",
            "total_packages", "delivered_packages", "delivery_rate",
            "open_incidents", "avg_evidence_score"
        ]
        for field in required_fields:
            assert field in data, f"Missing KPI field: {field}"
    
    def test_dashboard_stats_data_types(self, auth_headers):
        """Dashboard stats fields have correct data types"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/stats",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Integer fields
        int_fields = ["active_journeys", "closed_journeys", "total_journeys",
                      "total_packages", "delivered_packages", "open_incidents"]
        for field in int_fields:
            assert isinstance(data[field], int), f"{field} should be int"
        
        # Float fields
        float_fields = ["delivery_rate", "avg_evidence_score"]
        for field in float_fields:
            assert isinstance(data[field], (int, float)), f"{field} should be numeric"
    
    def test_dashboard_stats_with_date_range(self, auth_headers):
        """Dashboard stats respects date_from and date_to parameters"""
        response = requests.get(
            f"{BASE_URL}/api/dashboard/stats",
            params={"date_from": DATE_FROM, "date_to": DATE_TO},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # With data in range, should have some packages
        assert data["total_packages"] > 0, "Expected packages in date range"
        assert data["total_journeys"] > 0, "Expected journeys in date range"


class TestPackageSearch:
    """Tests for GET /api/packages/search - Package search functionality"""
    
    def test_package_search_returns_results(self, auth_headers):
        """Package search returns array of matching packages"""
        response = requests.get(
            f"{BASE_URL}/api/packages/search",
            params={"q": "CUBBO"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_package_search_short_query(self, auth_headers):
        """Package search with short query returns empty"""
        response = requests.get(
            f"{BASE_URL}/api/packages/search",
            params={"q": "A"},
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
